from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pit_lite.safety import SafetyError
from root_cause.artifacts import (
    ALLOWED_RESULTS,
    artifact_bundle_sha256,
    validate_csv_records,
    validate_json_document,
    write_artifacts,
)
from root_cause.attribution import (
    anonymous_loss_attribution,
    categorical_loss_shares,
    drawdown_episodes,
    paired_month_bootstrap,
)
from root_cause.data import DiagnosticContext
from root_cause.diagnostics import DiagnosticData
from root_cause.hypotheses import _added_quality_inputs, _capacity_inputs
from root_cause.statistics import (
    all_same_direction,
    clean_metrics,
    cluster_bootstrap_difference,
    cluster_bootstrap_value_difference,
    leave_one_bucket_out,
    normalize_exit_reason,
)


def _frame(
    value: float,
    *,
    count: int = 48,
    month_offset: int = 0,
    closed: bool = True,
) -> pd.DataFrame:
    months = pd.period_range("2020-01", periods=12, freq="M")
    records = []
    for index in range(count):
        month = months[(index + month_offset) % len(months)]
        records.append(
            {
                "code": f"bucket-{index % 4}",
                "ticker": f"bucket-{index % 4}",
                "sector": f"sector-{index % 2}",
                "signal_date": month.to_timestamp() + pd.Timedelta(days=index % 20),
                "exit_date": month.to_timestamp() + pd.Timedelta(days=21),
                "is_closed": closed,
                "net_return_pct": value,
                "negative_exit_burden": value,
                "holding_sessions": 20,
            }
        )
    return pd.DataFrame(records)


def test_clean_metrics_accepts_internal_code_without_ticker_alias() -> None:
    frame = _frame(0.01).drop(columns=["ticker"])
    metrics = clean_metrics(frame)
    assert metrics["closed_trade_count"] == len(frame)
    assert metrics["expectancy_per_trade"] == pytest.approx(0.01)
    assert metrics["sample_status"] == "SUFFICIENT"


def test_cluster_bootstrap_is_closed_only_for_observed_and_resamples() -> None:
    left = _frame(0.02)
    right = _frame(0.01)
    open_outlier = _frame(100.0, count=1, closed=False)
    result = cluster_bootstrap_difference(
        pd.concat([left, open_outlier], ignore_index=True),
        right,
        label="closed-only-regression",
    )
    assert result["observed_expectancy_difference"] == pytest.approx(0.01)
    assert result["ci_low"] == pytest.approx(0.01)
    assert result["ci_high"] == pytest.approx(0.01)
    assert result["direction_stable"] is True


def test_cluster_bootstrap_is_deterministic() -> None:
    left = _frame(0.03)
    right = _frame(-0.01)
    first = cluster_bootstrap_difference(left, right, label="deterministic")
    second = cluster_bootstrap_difference(left, right, label="deterministic")
    assert first == second


def test_cluster_bootstrap_uses_union_of_signal_month_clusters() -> None:
    left = _frame(0.02)
    right = _frame(0.01)
    right["signal_date"] = pd.to_datetime(right["signal_date"]) + pd.DateOffset(
        months=6
    )
    result = cluster_bootstrap_difference(left, right, label="union-months")
    assert result["signal_month_clusters"] == 18


def test_cluster_bootstrap_fails_closed_below_30_closed_per_arm() -> None:
    result = cluster_bootstrap_difference(
        _frame(0.02, count=29),
        _frame(0.01, count=48),
        label="small",
    )
    assert result["status"] == "INSUFFICIENT_SAMPLE"
    assert result["direction_stable"] is False


def test_generic_cluster_bootstrap_supports_exit_burden() -> None:
    left = _frame(0.8)
    right = _frame(0.2)
    result = cluster_bootstrap_value_difference(
        left,
        right,
        value_column="negative_exit_burden",
        label="burden",
    )
    assert result["observed_expectancy_difference"] == pytest.approx(0.6)
    assert result["direction_stable"] is True


def test_leave_one_bucket_out_requires_nonempty_evaluable_buckets() -> None:
    empty = pd.DataFrame(
        columns=[
            "code",
            "sector",
            "is_closed",
            "net_return_pct",
        ]
    )
    result = leave_one_bucket_out(
        empty,
        empty,
        column="code",
        expected_sign=1,
    )
    assert result["evaluable_leave_one_out_count"] == 0
    assert result["direction_stable"] is False


def test_leave_one_bucket_out_preserves_a_strong_direction() -> None:
    left = _frame(0.05, count=96)
    right = _frame(-0.01, count=96)
    result = leave_one_bucket_out(
        left,
        right,
        column="code",
        expected_sign=1,
    )
    assert result["evaluable_leave_one_out_count"] == 4
    assert result["direction_stable"] is True


@pytest.mark.parametrize(
    ("reason", "expected"),
    (
        ("stop_loss", "stop_loss"),
        ("stop_and_take_same_day_stop_first", "stop_loss"),
        ("stop_gap", "stop_gap"),
        ("take_profit", "take_profit"),
        ("take_profit_gap", "take_profit_gap"),
        ("max_holding", "max_holding"),
        ("premature_data_end_haircut", "data_end_or_haircut"),
        ("open_at_frozen_end", "other"),
    ),
)
def test_exit_reason_normalization(reason: str, expected: str) -> None:
    assert normalize_exit_reason(reason) == expected


def test_all_same_direction_is_fail_closed() -> None:
    assert all_same_direction([-1.0, -0.1], -1) is True
    assert all_same_direction([-1.0, 0.1], -1) is False
    assert all_same_direction([], -1) is False
    assert all_same_direction([None, -1.0], -1) is False


def test_drawdown_episode_definition_is_nonoverlapping_watermark() -> None:
    curve = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=8),
            "equity": [100, 90, 80, 101, 99, 70, 105, 103],
        }
    )
    episodes = drawdown_episodes(curve)
    assert len(episodes) == 3
    assert episodes[0]["drawdown"] == pytest.approx(70 / 101 - 1)
    assert episodes[1]["drawdown"] == pytest.approx(-0.20)


def test_anonymous_loss_attribution_exposes_no_bucket_identity() -> None:
    pnl = pd.DataFrame(
        {
            "code": ["a", "b", "a"],
            "pnl_jpy": [-10.0, -20.0, 5.0],
        }
    )
    result = anonymous_loss_attribution(pnl, "code")
    assert set(result) == {
        "distinct_loss_bucket_count",
        "top_loss_share",
        "top3_loss_share",
        "loss_hhi",
    }
    assert result["top_loss_share"] == pytest.approx(2 / 3)


def test_categorical_loss_shares_are_gross_negative_shares() -> None:
    pnl = pd.DataFrame(
        {
            "score": [90, 100, 120],
            "pnl_jpy": [-10.0, -30.0, 5.0],
        }
    )
    result = categorical_loss_shares(pnl, "score", [90, 100, 120])
    assert result == pytest.approx({"90": 0.25, "100": 0.75, "120": 0.0})


def test_paired_month_bootstrap_fails_closed_with_fewer_than_12_months() -> None:
    index = pd.period_range("2024-01", periods=11, freq="M").astype(str)
    result = paired_month_bootstrap(
        pd.Series(np.ones(11), index=index),
        pd.Series(np.zeros(11), index=index),
        seed=1,
        replicates=100,
    )
    assert result["status"] == "INSUFFICIENT_SAMPLE"


def test_aggregate_validator_rejects_identifier_keys() -> None:
    with pytest.raises(SafetyError):
        validate_json_document({"code": "forbidden"})
    with pytest.raises(SafetyError):
        validate_csv_records([{"ticker": "forbidden"}])


def test_artifact_bundle_hash_is_deterministic() -> None:
    csv_documents = {
        name: [{"metric": 1}]
        for name in ALLOWED_RESULTS
        if name.endswith(".csv")
    }
    json_documents = {
        name: {"metric": 1}
        for name in ALLOWED_RESULTS
        if name.endswith(".json")
    }
    first = artifact_bundle_sha256(csv_documents, json_documents, "report\n")
    second = artifact_bundle_sha256(csv_documents, json_documents, "report\n")
    assert first == second


def test_write_artifacts_enforces_exact_allowlist(tmp_path: Path) -> None:
    csv_documents = {
        name: [{"metric": 1}]
        for name in ALLOWED_RESULTS
        if name.endswith(".csv")
    }
    json_documents = {
        name: {"metric": 1}
        for name in ALLOWED_RESULTS
        if name.endswith(".json")
    }
    digest = write_artifacts(
        csv_documents,
        json_documents,
        "safe report",
        results_root=tmp_path / "results",
        report_path=tmp_path / "report.md",
    )
    assert len(digest) == 64
    assert {
        path.name for path in (tmp_path / "results").iterdir()
    } == ALLOWED_RESULTS
    assert json.loads(
        (tmp_path / "results" / "diagnostic_verdict.json").read_text()
    ) == {"metric": 1}


def test_write_artifacts_rejects_incomplete_allowlist(tmp_path: Path) -> None:
    with pytest.raises(SafetyError):
        write_artifacts(
            {"score_combination_metrics.csv": [{"metric": 1}]},
            {},
            "report",
            results_root=tmp_path / "results",
            report_path=tmp_path / "report.md",
        )


def test_hypothesis_quality_excludes_cross_split_outcomes() -> None:
    context = DiagnosticContext(
        run_id="synthetic",
        sessions=pd.bdate_range("2024-01-01", "2024-02-29"),
        splits={
            "validation": {
                "start": pd.Timestamp("2024-01-01"),
                "end": pd.Timestamp("2024-01-31"),
            }
        },
        selection_dates={},
        membership={},
        sectors={},
        bars={},
        frames={},
        signals={},
        ledgers={},
        curves={},
    )
    common = {
        "signal_date": pd.Timestamp("2024-01-10"),
        "entry_date": pd.Timestamp("2024-01-11"),
        "score": 90,
        "sector": "sector-a",
        "ticker": "internal",
        "shadow_status": "COMPLETE",
        "holding_sessions": 10,
        "mfe": 0.1,
        "mae": -0.1,
        "horizon_10": 0.0,
        "horizon_20": None,
        "horizon_40": None,
        "horizon_60": None,
        "is_closed": True,
        "net_return_pct": 0.01,
        "exit_reason": "max_holding",
        "normalized_exit_reason": "max_holding",
        "negative_exit_burden": 0.0,
    }
    shadows = pd.DataFrame(
        [
            {
                **common,
                "code": "inside",
                "origin_group": "ADDED_CODE",
                "exit_date": pd.Timestamp("2024-01-25"),
            },
            {
                **common,
                "code": "cross-boundary",
                "origin_group": "ADDED_CODE",
                "exit_date": pd.Timestamp("2024-02-02"),
            },
            {
                **common,
                "code": "control",
                "origin_group": "U15_STATIC_CODE",
                "exit_date": pd.Timestamp("2024-01-25"),
            },
        ]
    )
    decisions = shadows[
        ["code", "signal_date", "entry_date", "score", "sector"]
    ].copy()
    decisions["median_va_60"] = 1.0
    decisions["bitmask"] = 29
    decisions["origin_group"] = shadows["origin_group"]
    decisions["disposition"] = [
        "capacity_rejected",
        "capacity_rejected",
        "accepted",
    ]
    decisions["capacity_binding_session"] = True
    diagnostic = DiagnosticData(
        context=context,
        primary_replay={},
        shadows={"U50_PIT_LITE": shadows},
        accepted={},
        decisions={"U50_PIT_LITE": decisions},
        regime_daily={},
        position_pnl={},
        pnl_reconciliation={},
    )
    added, control = _added_quality_inputs(
        diagnostic,
        "U50_PIT_LITE",
        "validation",
    )
    rejected, accepted = _capacity_inputs(
        diagnostic,
        "U50_PIT_LITE",
        "validation",
    )
    assert added["code"].tolist() == ["inside"]
    assert control["code"].tolist() == ["control"]
    assert rejected["code"].tolist() == ["inside"]
    assert accepted["code"].tolist() == ["control"]
