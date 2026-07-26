from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pandas as pd


LAB_ROOT = Path(__file__).resolve().parents[1]
RESULTS = LAB_ROOT / "results"


def test_required_generated_artifacts_exist() -> None:
    required = [
        LAB_ROOT / "contracts" / "ver1_baseline_contract.json",
        LAB_ROOT / "docs" / "V2_RESEARCH_CONTRACT.md",
        LAB_ROOT / "data_manifest" / "DATA_AVAILABILITY_REPORT.md",
        LAB_ROOT / "data_manifest" / "data_manifest.json",
        LAB_ROOT / "config" / "universe_u15.yaml",
        LAB_ROOT / "config" / "universe_u50_proposal.yaml",
        LAB_ROOT / "config" / "universe_u100_proposal.yaml",
        LAB_ROOT / "reports" / "U15_BASELINE_REPORT.md",
        RESULTS / "u15_trades.csv",
        RESULTS / "u15_yearly_metrics.csv",
        RESULTS / "u15_monthly_signal_counts.csv",
        RESULTS / "u15_score_bucket_metrics.csv",
        RESULTS / "u15_ticker_metrics.csv",
        RESULTS / "u15_cost_sensitivity.csv",
    ]
    assert all(path.is_file() and path.stat().st_size > 0 for path in required)


def test_canonical_trade_output_obeys_execution_contract() -> None:
    trades = pd.read_csv(
        RESULTS / "u15_trades.csv",
        parse_dates=["signal_date", "entry_date", "exit_date"],
    )
    required_columns = {
        "trade_id",
        "run_id",
        "model_id",
        "universe_id",
        "base_commit",
        "point_in_time_universe",
        "survivorship_bias",
        "classification",
        "ticker",
        "signal_date",
        "score",
        "entry_date",
        "entry_raw_open",
        "entry_fill_price",
        "stop_price",
        "take_profit_price",
        "exit_date",
        "exit_reason",
        "holding_sessions",
        "net_return_pct",
        "cost_scenario",
        "path_policy",
    }
    assert required_columns <= set(trades.columns)
    assert set(trades["universe_id"]) == {"U15"}
    assert set(trades["point_in_time_universe"]) == {False}
    assert set(trades["survivorship_bias"]) == {True}
    assert set(trades["classification"]) == {
        "survivorship-biased exploratory evidence; not Formal Candidate"
    }
    assert set(trades["cost_scenario"]) == {"basic"}
    assert set(trades["path_policy"]) == {"conservative"}
    assert (trades["entry_date"] > trades["signal_date"]).all()
    assert trades["holding_sessions"].between(1, 60).all()
    assert set(trades["score"]) <= {90, 100, 120}
    assert trades[sorted(required_columns)].notna().all().all()


def test_no_overlapping_positions_for_same_ticker() -> None:
    trades = pd.read_csv(
        RESULTS / "u15_trades.csv",
        parse_dates=["signal_date", "entry_date", "exit_date"],
    )
    for _, group in trades.sort_values(["ticker", "entry_date"]).groupby("ticker"):
        previous_exit = None
        for row in group.itertuples(index=False):
            if previous_exit is not None:
                assert row.signal_date >= previous_exit
            previous_exit = row.exit_date


def test_empty_110_bucket_and_bias_labels_are_persisted() -> None:
    buckets = pd.read_csv(RESULTS / "u15_score_bucket_metrics.csv")
    row_110 = buckets.loc[buckets["score_bucket"] == 110].iloc[0]
    assert row_110["signal_count"] == 0
    assert row_110["trade_count"] == 0
    summary = json.loads((RESULTS / "u15_summary.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (LAB_ROOT / "data_manifest" / "data_manifest.json").read_text(encoding="utf-8")
    )
    assert "not Formal Candidate" in summary["classification"]
    assert manifest["point_in_time_universe_available"] is False
    assert summary["u50_u100_comparison_run"] is False


def test_every_result_csv_has_common_audit_labels() -> None:
    expected_classification = (
        "survivorship-biased exploratory evidence; not Formal Candidate"
    )
    for path in sorted(RESULTS.glob("*.csv")):
        frame = pd.read_csv(path)
        required = {
            "run_id",
            "model_id",
            "universe_id",
            "base_commit",
            "point_in_time_universe",
            "survivorship_bias",
            "classification",
        }
        assert required <= set(frame.columns), f"missing audit labels in {path.name}"
        assert frame["run_id"].nunique() == 1
        assert set(frame["model_id"]) == {"tgs_stable_v2_universe_lab"}
        assert set(frame["universe_id"]) == {"U15"}
        assert set(frame["base_commit"]) == {
            "43d5dd5aa6be3b0638b5af83976e61a214bd9c37"
        }
        assert set(frame["point_in_time_universe"].astype(str).str.lower()) == {"false"}
        assert set(frame["survivorship_bias"].astype(str).str.lower()) == {"true"}
        assert set(frame["classification"]) == {expected_classification}


def test_yearly_portfolio_return_uses_prior_calendar_close_anchor() -> None:
    curve = pd.read_csv(
        RESULTS / "u15_daily_equity.csv",
        parse_dates=["date"],
    ).sort_values("date")
    yearly = pd.read_csv(RESULTS / "u15_yearly_metrics.csv").set_index("year")

    assert set(yearly["trade_metric_basis"]) == {"exit_year"}
    assert set(yearly["portfolio_metric_basis"]) == {
        "calendar_year_with_prior_close_anchor"
    }
    assert set(yearly["exposure_metric_basis"]) == {
        "calendar_year_sessions_only"
    }

    previous_close = None
    for year, group in curve.groupby(curve["date"].dt.year, sort=True):
        year_end = float(group.iloc[-1]["equity"])
        year_start = (
            float(previous_close)
            if previous_close is not None
            else float(group.iloc[0]["equity"])
        )
        expected_return = year_end / year_start - 1.0
        actual_return = float(yearly.loc[year, "total_return"])
        assert math.isclose(actual_return, expected_return, abs_tol=1e-9)
        assert math.isclose(
            float(yearly.loc[year, "market_exposure"]),
            float(group["exposure"].mean()),
            abs_tol=1e-9,
        )
        assert int(yearly.loc[year, "maximum_concurrent_positions"]) == int(
            group["active_positions"].max()
        )
        previous_close = year_end


def test_yearly_trade_statistics_use_exit_year_not_signal_year() -> None:
    trades = pd.read_csv(
        RESULTS / "u15_trades.csv",
        parse_dates=["signal_date", "exit_date"],
    )
    yearly = pd.read_csv(RESULTS / "u15_yearly_metrics.csv").set_index("year")
    exit_year_counts = trades.groupby(trades["exit_date"].dt.year).size()
    signal_year_counts = trades.groupby(trades["signal_date"].dt.year).size()

    for year, row in yearly.iterrows():
        assert int(row["trade_count"]) == int(exit_year_counts.get(year, 0))
        assert int(row["signal_cohort_trade_count"]) == int(
            signal_year_counts.get(year, 0)
        )


def test_research_artifacts_contain_no_credential_shaped_values() -> None:
    credential_patterns = [
        re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
        re.compile(r"\bgh[opsu]_[A-Za-z0-9]{20,}\b"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r'"private_key"\s*:\s*"[^"]+'),
    ]
    for path in LAB_ROOT.rglob("*"):
        if not path.is_file() or "data/cache" in path.as_posix():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in credential_patterns:
            assert pattern.search(text) is None, f"credential-shaped value in {path}"
