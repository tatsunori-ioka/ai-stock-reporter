from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

import pit_lite.signals as signal_module
from pit_lite.metrics import (
    chronological_splits,
    economic_gate,
    split_metric_rows,
    yearly_metric_rows,
)
from tgs_stable_v2.config import COST_SCENARIOS


def synthetic_bars() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=60)
    raw = pd.Series(range(100, 160), dtype=float)
    adjusted = raw * 10.0
    return pd.DataFrame(
        {
            "Date": dates,
            "Code": "11110",
            "O": raw,
            "H": raw + 2,
            "L": raw - 2,
            "C": raw + 1,
            "Vo": 1_000.0,
            "Va": 1_000_000.0,
            "AdjFactor": 10.0,
            "AdjO": adjusted,
            "AdjH": adjusted + 20,
            "AdjL": adjusted - 20,
            "AdjC": adjusted + 10,
            "AdjVo": 100.0,
        }
    )


def test_signal_frame_keeps_adjusted_and_raw_price_bases_separate(
    monkeypatch,
) -> None:
    captured: list[pd.DataFrame] = []

    def capture(frame: pd.DataFrame) -> pd.DataFrame:
        captured.append(frame.copy())
        return pd.DataFrame(index=frame.index)

    monkeypatch.setattr(signal_module, "build_signal_frame", capture)
    bars = synthetic_bars()
    adjusted_result = signal_module.signal_frame_from_bars(bars, basis="adjusted")
    raw_result = signal_module.signal_frame_from_bars(bars, basis="raw")

    assert captured[0]["Open"].tolist() == bars["AdjO"].tolist()
    assert captured[0]["Close"].tolist() == bars["AdjC"].tolist()
    assert captured[0]["Volume"].tolist() == bars["AdjVo"].tolist()
    assert captured[1]["Open"].tolist() == bars["O"].tolist()
    assert captured[1]["Close"].tolist() == bars["C"].tolist()
    assert captured[1]["Volume"].tolist() == bars["Vo"].tolist()
    assert not captured[0]["Close"].equals(captured[1]["Close"])
    # Liquidity ranking remains provider Va and is basis-independent.
    assert adjusted_result["Va"].equals(raw_result["Va"])
    assert adjusted_result["median_va_60"].iloc[-1] == 1_000_000.0
    assert raw_result["median_va_60"].iloc[-1] == 1_000_000.0


def test_zero_basic_and_strict_cost_values_are_exact() -> None:
    zero = COST_SCENARIOS["zero"]
    basic = COST_SCENARIOS["basic"]
    strict = COST_SCENARIOS["strict"]
    assert (
        zero.commission_bps_per_side,
        zero.slippage_bps_per_side,
        zero.commission_rate,
        zero.slippage_rate,
        zero.round_trip_bps,
    ) == (0.0, 0.0, 0.0, 0.0, 0.0)
    assert (
        basic.commission_bps_per_side,
        basic.slippage_bps_per_side,
        basic.commission_rate,
        basic.slippage_rate,
        basic.round_trip_bps,
    ) == pytest.approx((10.0, 10.0, 0.001, 0.001, 40.0))
    assert (
        strict.commission_bps_per_side,
        strict.slippage_bps_per_side,
        strict.commission_rate,
        strict.slippage_rate,
        strict.round_trip_bps,
    ) == pytest.approx((20.0, 30.0, 0.002, 0.003, 100.0))


def test_chronological_splits_are_exact_60_20_20_nonoverlapping_sessions() -> None:
    sessions = pd.bdate_range("2024-01-02", periods=10)
    splits = chronological_splits(sessions)
    assert splits == {
        "development": {"start": sessions[0], "end": sessions[5]},
        "validation": {"start": sessions[6], "end": sessions[7]},
        "final_holdout": {"start": sessions[8], "end": sessions[9]},
    }
    covered = []
    for bounds in splits.values():
        covered.extend(
            sessions[
                (sessions >= bounds["start"])
                & (sessions <= bounds["end"])
            ].tolist()
        )
    assert covered == sessions.tolist()


def test_split_trade_metrics_exclude_cross_boundary_trade_from_split_metrics() -> None:
    sessions = pd.bdate_range("2024-01-02", periods=10)
    splits = chronological_splits(sessions)
    ledger = pd.DataFrame(
        [
            {
                "ticker": "11110",
                "code": "11110",
                "signal_date": sessions[1],
                "entry_date": sessions[2],
                "exit_date": sessions[3],
                "is_closed": True,
                "net_return_pct": 0.10,
                "holding_sessions": 2,
            },
            {
                "ticker": "22220",
                "code": "22220",
                "signal_date": sessions[4],
                "entry_date": sessions[5],
                "exit_date": sessions[6],
                "is_closed": True,
                "net_return_pct": -0.05,
                "holding_sessions": 2,
            },
            {
                "ticker": "33330",
                "code": "33330",
                "signal_date": sessions[6],
                "entry_date": sessions[6],
                "exit_date": sessions[7],
                "is_closed": True,
                "net_return_pct": 0.02,
                "holding_sessions": 2,
            },
            {
                "ticker": "44440",
                "code": "44440",
                "signal_date": sessions[8],
                "entry_date": sessions[8],
                "exit_date": sessions[9],
                "is_closed": True,
                "net_return_pct": 0.03,
                "holding_sessions": 2,
            },
        ]
    )
    curve = pd.DataFrame(
        {
            "date": sessions,
            "equity": [10_000_000 + index * 10_000 for index in range(10)],
            "cash": 5_000_000.0,
            "active_positions": 1,
            "cash_utilization": 0.5,
        }
    )
    rows = split_metric_rows("U50_PIT_LITE", ledger, curve, splits)
    lookup = {row["split"]: row for row in rows}
    assert lookup["development"]["signal_cohort_count"] == 2
    assert lookup["development"]["cross_boundary_excluded_count"] == 1
    assert lookup["development"]["trade_count"] == 1
    assert lookup["validation"]["signal_cohort_count"] == 1
    assert lookup["validation"]["cross_boundary_excluded_count"] == 0
    assert lookup["validation"]["trade_count"] == 1
    assert lookup["final_holdout"]["signal_cohort_count"] == 1
    assert lookup["final_holdout"]["cross_boundary_excluded_count"] == 0
    assert lookup["final_holdout"]["trade_count"] == 1


def test_yearly_metrics_use_signal_entry_and_exit_year_for_distinct_counts() -> None:
    signals = pd.DataFrame(
        {
            "signal_date": pd.to_datetime(["2023-12-29", "2024-12-30"]),
            "score": [90, 120],
        }
    )
    ledger = pd.DataFrame(
        [
            {
                "ticker": "11110",
                "code": "11110",
                "signal_date": "2023-12-29",
                "entry_date": "2024-01-04",
                "exit_date": "2024-06-03",
                "is_closed": True,
                "net_return_pct": 0.10,
                "holding_sessions": 20,
            },
            {
                "ticker": "22220",
                "code": "22220",
                "signal_date": "2024-12-30",
                "entry_date": "2024-12-31",
                "exit_date": "2025-02-03",
                "is_closed": True,
                "net_return_pct": -0.05,
                "holding_sessions": 20,
            },
        ]
    )
    curve = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2023-12-29", "2024-06-03", "2024-12-31", "2025-02-03"]
            ),
            "equity": [10_000_000, 11_000_000, 10_900_000, 10_400_000],
            "cash": [9_000_000, 10_000_000, 9_000_000, 10_400_000],
            "active_positions": [1, 0, 1, 0],
            "cash_utilization": [0.10, 0.0, 0.10, 0.0],
        }
    )
    rows = yearly_metric_rows(
        "U50_PIT_LITE",
        signals,
        ledger,
        curve,
        2023,
        2025,
    )
    by_year = {row["year"]: row for row in rows}
    assert (
        by_year[2023]["raw_signal_count"],
        by_year[2023]["accepted_entry_count"],
        by_year[2023]["trade_count"],
    ) == (1, 0, 0)
    assert (
        by_year[2024]["raw_signal_count"],
        by_year[2024]["accepted_entry_count"],
        by_year[2024]["trade_count"],
    ) == (1, 2, 1)
    assert (
        by_year[2025]["raw_signal_count"],
        by_year[2025]["accepted_entry_count"],
        by_year[2025]["trade_count"],
    ) == (0, 0, 1)
    for row in rows:
        assert row["raw_signal_count_basis"] == "signal_session_year"
        assert row["accepted_entry_count_basis"] == "entry_session_year"
        assert row["trade_metric_count_basis"] == "exit_session_year"


def gate_inputs(
    *,
    good_u50: bool,
    good_u100: bool,
) -> tuple[
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    baseline = {"cagr": 0.05, "maximum_drawdown": -0.20, "profit_factor": 1.0}
    good = {"cagr": 0.10, "maximum_drawdown": -0.30, "profit_factor": 1.30}
    bad = {"cagr": None, "maximum_drawdown": None, "profit_factor": None}
    flags = {"U50_PIT_LITE": good_u50, "U100_PIT_LITE": good_u100}
    universe_metrics = {
        "U15_ADJUSTED_STATIC": baseline,
        **{
            universe: dict(good if is_good else bad)
            for universe, is_good in flags.items()
        },
    }
    split_rows: list[dict[str, Any]] = []
    concentration: list[dict[str, Any]] = []
    for universe, is_good in flags.items():
        for split in ("validation", "final_holdout"):
            split_rows.append(
                {
                    "universe_id": universe,
                    "split": split,
                    "expectancy_per_trade": 1e-12 if is_good else None,
                    "profit_factor": 1.0000001 if is_good else None,
                }
            )
        concentration.extend(
            [
                {
                    "universe_id": universe,
                    "dimension": "ticker",
                    "top_bucket_trade_share": 0.15 if is_good else None,
                },
                {
                    "universe_id": universe,
                    "dimension": "sector",
                    "top_bucket_trade_share": 0.35 if is_good else None,
                },
            ]
        )
    return universe_metrics, split_rows, concentration


def test_economic_gate_exact_numeric_boundaries_pass_except_manual_dd_policy() -> None:
    result = economic_gate(*gate_inputs(good_u50=True, good_u100=True))
    assert result["verdict"] == "MIXED"
    for universe in ("U50_PIT_LITE", "U100_PIT_LITE"):
        item = result["universes"][universe]
        assert item["criteria_passed"] == item["criteria_total"] - 1
        assert item["criteria"]["maximum_drawdown_vs_u15"] is False
        assert item["maximum_drawdown_vs_u15_policy"] == (
            "MANUAL_THRESHOLD_REQUIRED_FAIL_CLOSED"
        )
        assert item["verdict"] == "MIXED"
    assert "EXPLORATORY_PROMISE_PASS" not in {
        item["verdict"] for item in result["universes"].values()
    }


def test_economic_gate_not_passed_requires_zero_machine_criteria() -> None:
    result = economic_gate(*gate_inputs(good_u50=False, good_u100=False))
    assert result["verdict"] == "NOT_PASSED"
    assert all(
        item["criteria_passed"] == 0
        and item["verdict"] == "NOT_PASSED"
        for item in result["universes"].values()
    )


def test_economic_gate_mixed_and_not_passed_roll_up_to_mixed() -> None:
    result = economic_gate(*gate_inputs(good_u50=True, good_u100=False))
    assert result["verdict"] == "MIXED"
    assert result["universes"]["U50_PIT_LITE"]["verdict"] == "MIXED"
    assert result["universes"]["U100_PIT_LITE"]["verdict"] == "NOT_PASSED"
    assert result["effect"] == (
        "no Formal Candidate, canary, purchase or production authorization"
    )
