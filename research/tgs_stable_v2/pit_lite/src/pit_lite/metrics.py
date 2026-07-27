from __future__ import annotations

import math
from typing import Any, Mapping

import pandas as pd

from tgs_stable_v2.metrics import (
    longest_no_signal_period,
    portfolio_metrics,
    trade_metrics,
)


def capital_metrics(curve: pd.DataFrame) -> dict[str, Any]:
    adapted = curve.copy()
    adapted["exposure"] = (pd.to_numeric(adapted["active_positions"]) > 0).astype(float)
    metrics = portfolio_metrics(adapted)
    metrics["mean_cash_utilization"] = float(
        pd.to_numeric(adapted["cash_utilization"], errors="coerce").mean()
    )
    metrics["minimum_cash"] = float(pd.to_numeric(adapted["cash"]).min())
    return metrics


def combined_metrics(
    ledger: pd.DataFrame,
    curve: pd.DataFrame,
    counters: Mapping[str, int],
) -> dict[str, Any]:
    return {
        **trade_metrics(ledger),
        **capital_metrics(curve),
        **{key: int(value) for key, value in counters.items()},
    }


def chronological_splits(sessions: pd.DatetimeIndex) -> dict[str, dict[str, Any]]:
    count = len(sessions)
    if count < 5:
        raise ValueError("not enough sessions for fixed splits")
    development_end = int(count * 0.60) - 1
    validation_end = int(count * 0.80) - 1
    return {
        "development": {
            "start": pd.Timestamp(sessions[0]),
            "end": pd.Timestamp(sessions[development_end]),
        },
        "validation": {
            "start": pd.Timestamp(sessions[development_end + 1]),
            "end": pd.Timestamp(sessions[validation_end]),
        },
        "final_holdout": {
            "start": pd.Timestamp(sessions[validation_end + 1]),
            "end": pd.Timestamp(sessions[-1]),
        },
    }


def split_metric_rows(
    universe_id: str,
    ledger: pd.DataFrame,
    curve: pd.DataFrame,
    splits: Mapping[str, Mapping[str, pd.Timestamp]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    signal_dates = pd.to_datetime(ledger["signal_date"]) if not ledger.empty else pd.Series(dtype="datetime64[ns]")
    entry_dates = pd.to_datetime(ledger["entry_date"]) if not ledger.empty else pd.Series(dtype="datetime64[ns]")
    exit_dates = pd.to_datetime(ledger["exit_date"]) if not ledger.empty else pd.Series(dtype="datetime64[ns]")
    curve_dates = pd.to_datetime(curve["date"])
    for split_name, bounds in splits.items():
        start = pd.Timestamp(bounds["start"])
        end = pd.Timestamp(bounds["end"])
        if ledger.empty:
            cohort = ledger
            contained = ledger
        else:
            cohort = ledger.loc[(signal_dates >= start) & (signal_dates <= end)]
            cohort_entries = pd.to_datetime(cohort["entry_date"])
            cohort_exits = pd.to_datetime(cohort["exit_date"])
            contained = cohort.loc[(cohort_entries >= start) & (cohort_exits <= end)]
        current_curve = curve.loc[(curve_dates >= start) & (curve_dates <= end)].copy()
        prior = curve.loc[curve_dates < start].tail(1)
        anchored = pd.concat([prior, current_curve], ignore_index=True)
        metrics = combined_metrics(contained, anchored, {})
        rows.append(
            {
                "universe_id": universe_id,
                "split": split_name,
                "start_session": start.date().isoformat(),
                "end_session": end.date().isoformat(),
                "signal_cohort_count": len(cohort),
                "cross_boundary_excluded_count": len(cohort) - len(contained),
                **metrics,
            }
        )
    return rows


def yearly_metric_rows(
    universe_id: str,
    signals: pd.DataFrame,
    ledger: pd.DataFrame,
    curve: pd.DataFrame,
    start_year: int,
    end_year: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    signal_dates = pd.to_datetime(signals["signal_date"])
    entry_dates = (
        pd.to_datetime(ledger["entry_date"])
        if not ledger.empty
        else pd.Series(dtype="datetime64[ns]")
    )
    exit_dates = pd.to_datetime(ledger["exit_date"]) if not ledger.empty else pd.Series(dtype="datetime64[ns]")
    curve_dates = pd.to_datetime(curve["date"])
    for year in range(start_year, end_year + 1):
        year_signals = signals.loc[signal_dates.dt.year == year]
        year_entries = (
            ledger.loc[entry_dates.dt.year == year] if not ledger.empty else ledger
        )
        year_ledger = ledger.loc[exit_dates.dt.year == year] if not ledger.empty else ledger
        current = curve.loc[curve_dates.dt.year == year]
        prior = curve.loc[curve_dates < pd.Timestamp(f"{year}-01-01")].tail(1)
        anchored = pd.concat([prior, current], ignore_index=True)
        rows.append(
            {
                "universe_id": universe_id,
                "year": year,
                "raw_signal_count": len(year_signals),
                "raw_signal_count_basis": "signal_session_year",
                "accepted_entry_count": len(year_entries),
                "accepted_entry_count_basis": "entry_session_year",
                "trade_metric_count_basis": "exit_session_year",
                **combined_metrics(year_ledger, anchored, {}),
            }
        )
    return rows


def score_metric_rows(
    universe_id: str,
    signals: pd.DataFrame,
    ledger: pd.DataFrame,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for score in (90, 100, 110, 120):
        selected_signals = signals.loc[pd.to_numeric(signals["score"]) == score]
        selected_ledger = (
            ledger.loc[pd.to_numeric(ledger["score"]) == score]
            if not ledger.empty
            else ledger
        )
        rows.append(
            {
                "universe_id": universe_id,
                "score_bucket": score,
                "raw_signal_count": len(selected_signals),
                **trade_metrics(selected_ledger),
            }
        )
    return rows


def concentration_rows(
    universe_id: str,
    ledger: pd.DataFrame,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dimension, column in (("ticker", "code"), ("sector", "sector")):
        if ledger.empty:
            shares = pd.Series(dtype=float)
        else:
            counts = ledger[column].fillna("").astype(str).value_counts()
            shares = counts / counts.sum()
        rows.append(
            {
                "universe_id": universe_id,
                "dimension": dimension,
                "accepted_entry_count": len(ledger),
                "distinct_bucket_count": len(shares),
                "top_bucket_trade_share": float(shares.max()) if not shares.empty else None,
                "trade_share_hhi": float((shares**2).sum()) if not shares.empty else None,
            }
        )
    return rows


def signal_frequency(
    signals: pd.DataFrame,
    ledger: pd.DataFrame,
    sessions: pd.DatetimeIndex,
) -> dict[str, Any]:
    elapsed_years = max(
        (pd.Timestamp(sessions[-1]) - pd.Timestamp(sessions[0])).days / 365.2425,
        1e-12,
    )
    no_signal = longest_no_signal_period(signals, sessions)
    return {
        "raw_signal_frequency_per_year": len(signals) / elapsed_years,
        "accepted_entry_frequency_per_year": len(ledger) / elapsed_years,
        "raw_signal_count": len(signals),
        "accepted_entry_count": len(ledger),
        "longest_no_signal_sessions": no_signal["sessions"],
        "longest_no_signal_calendar_days": no_signal["calendar_days"],
    }


def economic_gate(
    universe_metrics: Mapping[str, Mapping[str, Any]],
    split_rows: list[dict[str, Any]],
    concentration: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline = universe_metrics["U15_ADJUSTED_STATIC"]
    results: dict[str, Any] = {}
    split_lookup = {
        (row["universe_id"], row["split"]): row for row in split_rows
    }
    concentration_lookup = {
        (row["universe_id"], row["dimension"]): row for row in concentration
    }
    for universe_id in ("U50_PIT_LITE", "U100_PIT_LITE"):
        metrics = universe_metrics[universe_id]
        validation = split_lookup[(universe_id, "validation")]
        holdout = split_lookup[(universe_id, "final_holdout")]
        ticker = concentration_lookup[(universe_id, "ticker")]
        sector = concentration_lookup[(universe_id, "sector")]
        criteria = {
            "cagr_at_least_10pct": metrics.get("cagr") is not None
            and metrics["cagr"] >= 0.10,
            "maximum_drawdown_at_least_minus_30pct": metrics.get("maximum_drawdown")
            is not None
            and metrics["maximum_drawdown"] >= -0.30,
            "profit_factor_at_least_1_3": metrics.get("profit_factor") is not None
            and metrics["profit_factor"] >= 1.30,
            "validation_expectancy_positive": validation.get("expectancy_per_trade")
            is not None
            and validation["expectancy_per_trade"] > 0,
            "validation_profit_factor_above_1": validation.get("profit_factor")
            is not None
            and validation["profit_factor"] > 1.0,
            "holdout_expectancy_positive": holdout.get("expectancy_per_trade") is not None
            and holdout["expectancy_per_trade"] > 0,
            "holdout_profit_factor_above_1": holdout.get("profit_factor") is not None
            and holdout["profit_factor"] > 1.0,
            "cagr_advantage_over_u15_at_least_5pp": metrics.get("cagr") is not None
            and baseline.get("cagr") is not None
            and metrics["cagr"] - baseline["cagr"] >= 0.05,
            "maximum_drawdown_vs_u15": False,
            "top_ticker_trade_share_at_most_15pct": ticker.get(
                "top_bucket_trade_share"
            )
            is not None
            and ticker["top_bucket_trade_share"] <= 0.15,
            "top_sector_trade_share_at_most_35pct": sector.get(
                "top_bucket_trade_share"
            )
            is not None
            and sector["top_bucket_trade_share"] <= 0.35,
        }
        passed = sum(bool(value) for value in criteria.values())
        if all(criteria.values()):
            verdict = "EXPLORATORY_PROMISE_PASS"
        elif passed == 0:
            verdict = "NOT_PASSED"
        else:
            verdict = "MIXED"
        results[universe_id] = {
            "criteria": criteria,
            "maximum_drawdown_delta_vs_u15": (
                metrics["maximum_drawdown"] - baseline["maximum_drawdown"]
                if metrics.get("maximum_drawdown") is not None
                and baseline.get("maximum_drawdown") is not None
                else None
            ),
            "maximum_drawdown_vs_u15_policy": "MANUAL_THRESHOLD_REQUIRED_FAIL_CLOSED",
            "criteria_passed": passed,
            "criteria_total": len(criteria),
            "verdict": verdict,
        }
    verdicts = {item["verdict"] for item in results.values()}
    if "EXPLORATORY_PROMISE_PASS" in verdicts:
        overall = "EXPLORATORY_PROMISE_PASS"
    elif "MIXED" in verdicts:
        overall = "MIXED"
    else:
        overall = "NOT_PASSED"
    return {
        "verdict": overall,
        "universes": results,
        "effect": "no Formal Candidate, canary, purchase or production authorization",
    }
