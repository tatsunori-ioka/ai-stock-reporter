from __future__ import annotations

from typing import Any

import pandas as pd

from .contract import CONTRACT
from .diagnostics import (
    EXPANDED_UNIVERSES,
    DiagnosticData,
    _anchored_curve,
    _bounds,
    capacity_quality_frames,
)
from .attribution import maximum_drawdown_for_window
from .statistics import (
    MIN_TRADES,
    cluster_bootstrap_value_difference,
    concentration,
    finite_or_none,
    leave_one_bucket_out,
    signal_in_split,
    split_contained,
)


REQUIRED_SPLITS = tuple(
    CONTRACT["robust_hypothesis_policy"]["required_splits"]
)
PRIORITY = tuple(CONTRACT["robust_hypothesis_policy"]["hypothesis_priority"])
MAX_ACTIONABLE = int(
    CONTRACT["robust_hypothesis_policy"]["maximum_actionable_hypotheses"]
)


def _closed(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return frame.loc[frame["is_closed"].astype(bool)].copy()


def _evaluate_pair(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    value_column: str,
    expected_sign: int,
    label: str,
) -> dict[str, Any]:
    bootstrap = cluster_bootstrap_value_difference(
        left,
        right,
        value_column=value_column,
        label=label,
    )
    ticker_loo = leave_one_bucket_out(
        left,
        right,
        column="code",
        expected_sign=expected_sign,
        value_column=value_column,
    )
    sector_loo = leave_one_bucket_out(
        left,
        right,
        column="sector",
        expected_sign=expected_sign,
        value_column=value_column,
    )
    left_closed = _closed(left)
    right_closed = _closed(right)
    left_ticker = concentration(left_closed, "code")
    right_ticker = concentration(right_closed, "code")
    left_sector = concentration(left_closed, "sector")
    right_sector = concentration(right_closed, "sector")
    observed = bootstrap["observed_expectancy_difference"]
    direction_matches = (
        observed is not None
        and (
            (expected_sign > 0 and float(observed) > 0)
            or (expected_sign < 0 and float(observed) < 0)
        )
    )
    sample_sufficient = (
        int(bootstrap["left_closed_trades"]) >= MIN_TRADES
        and int(bootstrap["right_closed_trades"]) >= MIN_TRADES
        and bootstrap["status"] == "SUFFICIENT"
    )
    ticker_loo_evaluable = (
        int(ticker_loo["bucket_count"]) > 0
        and int(ticker_loo["evaluable_leave_one_out_count"])
        == int(ticker_loo["bucket_count"])
    )
    sector_loo_evaluable = (
        int(sector_loo["bucket_count"]) > 0
        and int(sector_loo["evaluable_leave_one_out_count"])
        == int(sector_loo["bucket_count"])
    )
    concentration_ok = all(
        value is not None and float(value) <= limit
        for value, limit in (
            (
                left_ticker["top_bucket_share"],
                CONTRACT["robust_hypothesis_policy"][
                    "maximum_top_ticker_share"
                ],
            ),
            (
                right_ticker["top_bucket_share"],
                CONTRACT["robust_hypothesis_policy"][
                    "maximum_top_ticker_share"
                ],
            ),
            (
                left_sector["top_bucket_share"],
                CONTRACT["robust_hypothesis_policy"][
                    "maximum_top_sector_share"
                ],
            ),
            (
                right_sector["top_bucket_share"],
                CONTRACT["robust_hypothesis_policy"][
                    "maximum_top_sector_share"
                ],
            ),
        )
    )
    fully_evaluable = (
        sample_sufficient and ticker_loo_evaluable and sector_loo_evaluable
    )
    passes = (
        fully_evaluable
        and direction_matches
        and bool(bootstrap["direction_stable"])
        and bool(ticker_loo["direction_stable"])
        and bool(sector_loo["direction_stable"])
        and concentration_ok
    )
    return {
        "left_closed_count": int(bootstrap["left_closed_trades"]),
        "right_closed_count": int(bootstrap["right_closed_trades"]),
        "signal_month_cluster_count": int(
            bootstrap["signal_month_clusters"]
        ),
        "observed_mean_difference": observed,
        "expected_direction": "positive" if expected_sign > 0 else "negative",
        "observed_direction_matches": bool(direction_matches),
        "bootstrap_status": bootstrap["status"],
        "bootstrap_ci_low": bootstrap["ci_low"],
        "bootstrap_ci_high": bootstrap["ci_high"],
        "bootstrap_valid_replicate_fraction": bootstrap[
            "valid_replicate_fraction"
        ],
        "bootstrap_same_direction_fraction": bootstrap[
            "same_direction_fraction"
        ],
        "bootstrap_direction_stable": bool(
            bootstrap["direction_stable"]
        ),
        "ticker_leave_one_out_evaluable": bool(ticker_loo_evaluable),
        "ticker_leave_one_out_direction_stable": bool(
            ticker_loo["direction_stable"]
        ),
        "ticker_leave_one_out_minimum_effect": ticker_loo[
            "minimum_effect"
        ],
        "ticker_leave_one_out_maximum_effect": ticker_loo[
            "maximum_effect"
        ],
        "sector_leave_one_out_evaluable": bool(sector_loo_evaluable),
        "sector_leave_one_out_direction_stable": bool(
            sector_loo["direction_stable"]
        ),
        "sector_leave_one_out_minimum_effect": sector_loo[
            "minimum_effect"
        ],
        "sector_leave_one_out_maximum_effect": sector_loo[
            "maximum_effect"
        ],
        "left_top_ticker_share": left_ticker["top_bucket_share"],
        "right_top_ticker_share": right_ticker["top_bucket_share"],
        "left_top_sector_share": left_sector["top_bucket_share"],
        "right_top_sector_share": right_sector["top_bucket_share"],
        "concentration_thresholds_pass": bool(concentration_ok),
        "fully_evaluable": bool(fully_evaluable),
        "passes_all_robust_conditions": bool(passes),
    }


def _added_quality_inputs(
    data: DiagnosticData,
    universe_id: str,
    split: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    current = split_contained(
        data.shadows[universe_id],
        _bounds(data.context, split),
    )
    return (
        current.loc[current["origin_group"] == "ADDED_CODE"].copy(),
        current.loc[current["origin_group"] == "U15_STATIC_CODE"].copy(),
    )


def _capacity_inputs(
    data: DiagnosticData,
    universe_id: str,
    split: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    current = split_contained(
        capacity_quality_frames(data, universe_id),
        _bounds(data.context, split),
    )
    return (
        current.loc[current["disposition"] == "capacity_rejected"].copy(),
        current.loc[
            (current["disposition"] == "accepted")
            & current["capacity_binding_session"].astype(bool)
        ].copy(),
    )


def _exposure_inputs(
    data: DiagnosticData,
    universe_id: str,
    split: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ledger = split_contained(
        data.accepted[universe_id],
        _bounds(data.context, split),
    )
    utilization = (
        data.context.curves[universe_id]
        .set_index("date")["cash_utilization"]
        .rename("signal_cash_utilization")
    )
    current = ledger.merge(
        utilization,
        left_on="signal_date",
        right_index=True,
        how="left",
        validate="many_to_one",
    )
    threshold = float(
        CONTRACT["diagnostic_hypothesis_estimands"]["C_HIGH_EXPOSURE"][
            "high_exposure_threshold"
        ]
    )
    return (
        current.loc[
            pd.to_numeric(current["signal_cash_utilization"]) >= threshold
        ].copy(),
        current.loc[
            pd.to_numeric(current["signal_cash_utilization"]) < threshold
        ].copy(),
    )


def _score_inputs(
    data: DiagnosticData,
    universe_id: str,
    split: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    current = split_contained(
        data.accepted[universe_id],
        _bounds(data.context, split),
    )
    score = pd.to_numeric(current["score"], errors="coerce")
    return (
        current.loc[score == 120].copy(),
        current.loc[score.isin((90, 100))].copy(),
    )


def _drawdown_support(
    data: DiagnosticData,
    universe_id: str,
    split: str,
) -> dict[str, Any]:
    bounds = _bounds(data.context, split)
    start, end = pd.Timestamp(bounds["start"]), pd.Timestamp(bounds["end"])
    expanded = maximum_drawdown_for_window(
        _anchored_curve(data.context.curves[universe_id], start, end)
    )
    baseline = maximum_drawdown_for_window(
        _anchored_curve(
            data.context.curves["U15_ADJUSTED_STATIC"],
            start,
            end,
        )
    )
    worse = (
        expanded is not None
        and baseline is not None
        and float(expanded) < float(baseline)
    )
    return {
        "expanded_maximum_drawdown": finite_or_none(expanded),
        "u15_adjusted_maximum_drawdown": finite_or_none(baseline),
        "expanded_minus_u15_drawdown": (
            finite_or_none(float(expanded) - float(baseline))
            if expanded is not None and baseline is not None
            else None
        ),
        "expanded_drawdown_worse": bool(worse),
    }


def evaluate_hypotheses(data: DiagnosticData) -> dict[str, Any]:
    all_results: dict[str, Any] = {}
    definitions = {
        "A_ADDED_SIGNAL_QUALITY": (
            _added_quality_inputs,
            "net_return_pct",
            -1,
        ),
        "B_CAPACITY_PRIORITY": (
            _capacity_inputs,
            "net_return_pct",
            1,
        ),
        "C_HIGH_EXPOSURE": (
            _exposure_inputs,
            "net_return_pct",
            -1,
        ),
        "D_EXIT_ATTRIBUTION": (
            _added_quality_inputs,
            "negative_exit_burden",
            1,
        ),
        "E_SCORE_MONOTONICITY": (
            _score_inputs,
            "net_return_pct",
            -1,
        ),
    }
    for hypothesis_id in PRIORITY:
        factory, value_column, expected_sign = definitions[hypothesis_id]
        evaluations: dict[str, Any] = {}
        for universe_id in EXPANDED_UNIVERSES:
            evaluations[universe_id] = {}
            for split in REQUIRED_SPLITS:
                left, right = factory(data, universe_id, split)
                current = _evaluate_pair(
                    left,
                    right,
                    value_column=value_column,
                    expected_sign=expected_sign,
                    label=f"{hypothesis_id}:{universe_id}:{split}",
                )
                if hypothesis_id == "C_HIGH_EXPOSURE":
                    current["drawdown_support"] = _drawdown_support(
                        data,
                        universe_id,
                        split,
                    )
                    current["passes_all_robust_conditions"] = bool(
                        current["passes_all_robust_conditions"]
                        and current["drawdown_support"][
                            "expanded_drawdown_worse"
                        ]
                    )
                evaluations[universe_id][split] = current
        flattened = [
            evaluations[universe_id][split]
            for universe_id in EXPANDED_UNIVERSES
            for split in REQUIRED_SPLITS
        ]
        fully_evaluable = all(
            item["fully_evaluable"] for item in flattened
        )
        passes = fully_evaluable and all(
            item["passes_all_robust_conditions"] for item in flattened
        )
        all_results[hypothesis_id] = {
            "status": (
                "ACTIONABLE_DIAGNOSTIC_HYPOTHESIS"
                if passes
                else (
                    "EVALUATED_NOT_ACTIONABLE"
                    if fully_evaluable
                    else "INSUFFICIENT_SAMPLE"
                )
            ),
            "fully_evaluable_across_required_universes_and_splits": bool(
                fully_evaluable
            ),
            "passes_all_robust_conditions": bool(passes),
            "estimand": CONTRACT["diagnostic_hypothesis_estimands"][
                hypothesis_id
            ],
            "evaluations": evaluations,
        }

    actionable_all = [
        hypothesis_id
        for hypothesis_id in PRIORITY
        if all_results[hypothesis_id]["passes_all_robust_conditions"]
    ]
    actionable = actionable_all[:MAX_ACTIONABLE]
    any_evaluable = any(
        item["fully_evaluable_across_required_universes_and_splits"]
        for item in all_results.values()
    )
    if actionable:
        verdict = "ACTIONABLE_DIAGNOSTIC_HYPOTHESIS"
    elif any_evaluable:
        verdict = "NO_ACTIONABLE_DIAGNOSTIC_HYPOTHESIS"
    else:
        verdict = "DATA_OR_SAMPLE_INSUFFICIENT"
    if len(actionable_all) >= 2:
        cause = "F_MULTIPLE_FACTORS"
    elif len(actionable_all) == 1:
        cause = actionable_all[0][0]
    else:
        cause = "G_CLEAR_CAUSE_NOT_IDENTIFIED"
    return {
        "diagnostic_verdict": verdict,
        "underperformance_cause_classification": cause,
        "actionable_hypotheses": actionable,
        "actionable_hypothesis_count_before_cap": len(actionable_all),
        "maximum_actionable_hypotheses": MAX_ACTIONABLE,
        "hypotheses": all_results,
    }
