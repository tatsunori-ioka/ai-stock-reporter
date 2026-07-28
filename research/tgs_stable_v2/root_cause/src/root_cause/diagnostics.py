from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd

from tgs_stable_v2.config import COST_SCENARIOS

from .attribution import (
    anonymous_loss_attribution,
    categorical_loss_shares,
    drawdown_episodes,
    maximum_drawdown_for_window,
    position_daily_pnl,
    verify_daily_pnl_reconciliation,
)
from .contract import CONTRACT
from .data import COMPONENTS, PRIMARY_UNIVERSES, DiagnosticContext
from .replay import (
    build_shadow_outcomes,
    classify_signal_dispositions,
    verify_frozen_primary_replay,
)
from .statistics import (
    clean_metrics,
    cluster_bootstrap_difference,
    concentration,
    finite_or_none,
    loss_concentration,
    normalize_exit_reason,
    signal_in_split,
    split_contained,
)


SPLIT_ORDER = ("overall", "development", "validation", "final_holdout")
EXPANDED_UNIVERSES = ("U50_PIT_LITE", "U100_PIT_LITE")
SCORE_MASKS = (15, 23, 29, 30, 31)
SCORE_GROUPS: tuple[tuple[str, tuple[int, ...] | None], ...] = (
    ("ALL", None),
    ("90", (90,)),
    ("100", (100,)),
    ("120", (120,)),
)
EXIT_REASONS = tuple(CONTRACT["exit_diagnostic"]["reason_groups"])
DISPOSITION_ROWS = (
    "accepted_all",
    "accepted_binding",
    "capacity_rejected",
    "duplicate_rejected",
    "missing_next_session",
    "invalid_bar",
)
COMMISSION = COST_SCENARIOS["basic"].commission_rate


@dataclass
class DiagnosticData:
    context: DiagnosticContext
    primary_replay: dict[str, Any]
    shadows: dict[str, pd.DataFrame]
    accepted: dict[str, pd.DataFrame]
    decisions: dict[str, pd.DataFrame]
    regime_daily: dict[str, pd.DataFrame]
    position_pnl: dict[str, pd.DataFrame]
    pnl_reconciliation: dict[str, dict[str, Any]]


def _bounds(
    context: DiagnosticContext,
    split: str,
) -> dict[str, pd.Timestamp]:
    if split == "overall":
        return {
            "start": pd.Timestamp(context.sessions[0]),
            "end": pd.Timestamp(context.sessions[-1]),
        }
    return context.splits[split]


def _closed(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return frame.loc[frame["is_closed"].astype(bool)].copy()


def _score_from_mask(mask: int) -> int:
    weights = CONTRACT["score_bitmask"]["score_weights"]
    values = CONTRACT["score_bitmask"]["bit_values"]
    return sum(
        int(weights[name])
        for name in COMPONENTS
        if int(mask) & int(values[name])
    )


def _component_flags(mask: int) -> dict[str, bool]:
    values = CONTRACT["score_bitmask"]["bit_values"]
    return {
        f"has_{name}": bool(int(mask) & int(values[name]))
        for name in COMPONENTS
    }


def _enrich_shadow(shadow: pd.DataFrame) -> pd.DataFrame:
    result = shadow.copy()
    result["ticker"] = result["code"]
    result["normalized_exit_reason"] = result["exit_reason"].map(
        normalize_exit_reason
    )
    returns = pd.to_numeric(result["net_return_pct"], errors="coerce")
    result["negative_exit_burden"] = (
        result["normalized_exit_reason"].isin(("stop_loss", "stop_gap"))
        | (
            (result["normalized_exit_reason"] == "max_holding")
            & (returns < 0)
        )
    ).astype(float)
    return result


def _enrich_accepted(
    context: DiagnosticContext,
    universe_id: str,
    shadow: pd.DataFrame,
) -> pd.DataFrame:
    ledger = context.ledgers[universe_id].copy()
    signal_columns = [
        "code",
        "signal_date",
        "bitmask",
        "origin_group",
        *COMPONENTS,
    ]
    ledger = ledger.merge(
        context.signals[universe_id][signal_columns],
        on=["code", "signal_date"],
        how="left",
        validate="one_to_one",
    )
    if ledger["bitmask"].isna().any():
        raise RuntimeError(f"{universe_id} accepted trade lacks signal components")
    diagnostic_columns = [
        "code",
        "signal_date",
        "shadow_status",
        "mfe",
        "mae",
        "horizon_10",
        "horizon_20",
        "horizon_40",
        "horizon_60",
    ]
    ledger = ledger.merge(
        shadow[diagnostic_columns],
        on=["code", "signal_date"],
        how="left",
        validate="one_to_one",
    )
    ledger["normalized_exit_reason"] = ledger["exit_reason"].map(
        normalize_exit_reason
    )
    ledger["net_pnl_jpy"] = pd.to_numeric(ledger["shares"]) * (
        pd.to_numeric(ledger["exit_fill_price"]) * (1.0 - COMMISSION)
        - pd.to_numeric(ledger["entry_fill_price"]) * (1.0 + COMMISSION)
    )
    closed = ledger["is_closed"].astype(bool)
    accepted_returns = pd.to_numeric(
        ledger.loc[closed, "net_return_pct"], errors="coerce"
    ).to_numpy()
    shadow_returns = pd.to_numeric(
        shadow.set_index(["code", "signal_date"])
        .loc[
            list(
                zip(
                    ledger.loc[closed, "code"],
                    ledger.loc[closed, "signal_date"],
                )
            ),
            "net_return_pct",
        ],
        errors="coerce",
    ).to_numpy()
    if not np.allclose(
        accepted_returns,
        shadow_returns,
        rtol=1e-11,
        atol=1e-12,
        equal_nan=True,
    ):
        raise RuntimeError(f"{universe_id} accepted one-shot return mismatch")
    return ledger


def build_regime_daily(
    context: DiagnosticContext,
    universe_id: str,
    decisions: pd.DataFrame,
) -> pd.DataFrame:
    sessions = context.sessions
    valid_members: list[pd.Series] = []
    above: list[pd.Series] = []
    macd: list[pd.Series] = []
    returns: list[pd.Series] = []
    for code, frame in sorted(context.frames[universe_id].items()):
        member = frame["universe_member"].reindex(sessions).fillna(False).astype(bool)
        close = pd.to_numeric(frame["Close"], errors="coerce")
        valid = member & close.reindex(sessions).gt(0).fillna(False)
        valid_members.append(valid.rename(code))
        above.append(
            frame["weekly_above_200ma"]
            .reindex(sessions)
            .where(valid)
            .astype(float)
            .rename(code)
        )
        macd.append(
            frame["weekly_macd_uptrend"]
            .reindex(sessions)
            .where(valid)
            .astype(float)
            .rename(code)
        )
        returns.append(close.pct_change().reindex(sessions).where(valid).rename(code))
    valid_member_frame = pd.concat(valid_members, axis=1)
    above_frame = pd.concat(above, axis=1)
    macd_frame = pd.concat(macd, axis=1)
    return_frame = pd.concat(returns, axis=1)
    active_count = valid_member_frame.sum(axis=1)
    signal_count = (
        context.signals[universe_id]
        .groupby("signal_date")
        .size()
        .reindex(sessions, fill_value=0)
    )
    disposition_counts = (
        decisions.dropna(subset=["entry_date"])
        .groupby(["entry_date", "disposition"])
        .size()
        .unstack(fill_value=0)
        .reindex(sessions, fill_value=0)
    )
    curve = (
        context.curves[universe_id]
        .set_index("date")
        .reindex(sessions)
    )
    result = pd.DataFrame(
        {
            "date": sessions,
            "active_member_count": active_count.to_numpy(),
            "active_member_weekly_above_200ma_share": above_frame.mean(
                axis=1, skipna=True
            ).to_numpy(),
            "active_member_macd_uptrend_share": macd_frame.mean(
                axis=1, skipna=True
            ).to_numpy(),
            "cross_sectional_median_adjusted_return": return_frame.median(
                axis=1, skipna=True
            ).to_numpy(),
            "cross_sectional_adjusted_return_population_std": return_frame.std(
                axis=1, skipna=True, ddof=0
            ).to_numpy(),
            "raw_signal_count": signal_count.to_numpy(),
            "signal_breadth": (
                signal_count / active_count.replace(0, np.nan)
            ).to_numpy(),
            "cash_utilization": pd.to_numeric(
                curve["cash_utilization"], errors="coerce"
            ).to_numpy(),
            "active_positions": pd.to_numeric(
                curve["active_positions"], errors="coerce"
            ).to_numpy(),
            "equity": pd.to_numeric(curve["equity"], errors="coerce").to_numpy(),
        }
    )
    for disposition in CONTRACT["capacity_diagnostic"]["dispositions"]:
        result[f"{disposition}_count"] = (
            disposition_counts[disposition].to_numpy()
            if disposition in disposition_counts
            else 0
        )
    return result


def build_diagnostic_data(context: DiagnosticContext) -> DiagnosticData:
    primary_replay = verify_frozen_primary_replay(context)
    shadows: dict[str, pd.DataFrame] = {}
    accepted: dict[str, pd.DataFrame] = {}
    decisions: dict[str, pd.DataFrame] = {}
    regime_daily: dict[str, pd.DataFrame] = {}
    position_pnl_frames: dict[str, pd.DataFrame] = {}
    reconciliation: dict[str, dict[str, Any]] = {}
    for universe_id in PRIMARY_UNIVERSES:
        shadows[universe_id] = _enrich_shadow(
            build_shadow_outcomes(context, universe_id)
        )
        accepted[universe_id] = _enrich_accepted(
            context,
            universe_id,
            shadows[universe_id],
        )
        decisions[universe_id] = classify_signal_dispositions(
            context,
            universe_id,
        )
        regime_daily[universe_id] = build_regime_daily(
            context,
            universe_id,
            decisions[universe_id],
        )
        position_pnl_frames[universe_id] = position_daily_pnl(
            context,
            universe_id,
        )
        reconciliation[universe_id] = verify_daily_pnl_reconciliation(
            context,
            universe_id,
            position_pnl_frames[universe_id],
        )
    return DiagnosticData(
        context=context,
        primary_replay=primary_replay,
        shadows=shadows,
        accepted=accepted,
        decisions=decisions,
        regime_daily=regime_daily,
        position_pnl=position_pnl_frames,
        pnl_reconciliation=reconciliation,
    )


def score_combination_rows(data: DiagnosticData) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for universe_id in PRIMARY_UNIVERSES:
        signals = data.context.signals[universe_id]
        ledger = data.accepted[universe_id]
        for split in SPLIT_ORDER:
            bounds = _bounds(data.context, split)
            split_signals = signal_in_split(signals, bounds)
            accepted_cohort = signal_in_split(ledger, bounds)
            contained = split_contained(ledger, bounds)
            for mask in SCORE_MASKS:
                current_signals = split_signals.loc[
                    pd.to_numeric(split_signals["bitmask"]) == mask
                ]
                current_cohort = accepted_cohort.loc[
                    pd.to_numeric(accepted_cohort["bitmask"]) == mask
                ]
                current = contained.loc[
                    pd.to_numeric(contained["bitmask"]) == mask
                ]
                metrics = clean_metrics(current)
                closed = _closed(current)
                exit_counts = (
                    closed["normalized_exit_reason"].value_counts().to_dict()
                    if not closed.empty
                    else {}
                )
                ticker = concentration(closed, "code")
                sector = concentration(closed, "sector")
                ticker_loss = loss_concentration(closed, "code")
                sector_loss = loss_concentration(closed, "sector")
                rows.append(
                    {
                        "universe_id": universe_id,
                        "split": split,
                        "bitmask": mask,
                        "bit_pattern": format(mask, "05b"),
                        "score": _score_from_mask(mask),
                        **_component_flags(mask),
                        "raw_signal_count": int(len(current_signals)),
                        "accepted_signal_cohort_count": int(len(current_cohort)),
                        "contained_trade_count": int(len(current)),
                        "cross_boundary_excluded_count": int(
                            len(current_cohort) - len(current)
                        ),
                        **metrics,
                        **{
                            f"{reason}_exit_count": int(
                                exit_counts.get(reason, 0)
                            )
                            for reason in EXIT_REASONS
                        },
                        "ticker_distinct_count": ticker["distinct_bucket_count"],
                        "ticker_top_trade_share": ticker["top_bucket_share"],
                        "ticker_trade_hhi": ticker["hhi"],
                        "sector_distinct_count": sector["distinct_bucket_count"],
                        "sector_top_trade_share": sector["top_bucket_share"],
                        "sector_trade_hhi": sector["hhi"],
                        "ticker_top_loss_share": ticker_loss["top_loss_share"],
                        "ticker_loss_hhi": ticker_loss["loss_hhi"],
                        "sector_top_loss_share": sector_loss["top_loss_share"],
                        "sector_loss_hhi": sector_loss["loss_hhi"],
                    }
                )
    return rows


def _mean(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return finite_or_none(values.mean()) if not values.empty else None


def exit_reason_rows(data: DiagnosticData) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for universe_id in PRIMARY_UNIVERSES:
        ledger = data.accepted[universe_id]
        for split in ("overall", "validation", "final_holdout"):
            contained = split_contained(ledger, _bounds(data.context, split))
            for score_label, scores in SCORE_GROUPS:
                score_frame = (
                    contained
                    if scores is None
                    else contained.loc[
                        pd.to_numeric(contained["score"]).isin(scores)
                    ]
                )
                closed_score = _closed(score_frame)
                total_pnl = float(
                    pd.to_numeric(
                        closed_score["net_pnl_jpy"], errors="coerce"
                    ).sum()
                )
                for reason in EXIT_REASONS:
                    current = closed_score.loc[
                        closed_score["normalized_exit_reason"] == reason
                    ]
                    metrics = clean_metrics(current)
                    current_pnl = float(
                        pd.to_numeric(
                            current["net_pnl_jpy"], errors="coerce"
                        ).sum()
                    )
                    row: dict[str, Any] = {
                        "universe_id": universe_id,
                        "split": split,
                        "score_group": score_label,
                        "exit_reason_group": reason,
                        "exit_count": int(len(current)),
                        "total_net_pnl_jpy": current_pnl,
                        "share_of_score_group_net_pnl": (
                            finite_or_none(current_pnl / total_pnl)
                            if total_pnl != 0
                            else None
                        ),
                        **metrics,
                        "mean_mfe": _mean(current, "mfe"),
                        "mean_mae": _mean(current, "mae"),
                    }
                    for horizon in (10, 20, 40, 60):
                        values = pd.to_numeric(
                            current[f"horizon_{horizon}"], errors="coerce"
                        ).dropna()
                        row[f"horizon_{horizon}_available_count"] = int(
                            len(values)
                        )
                        row[f"horizon_{horizon}_mean_unrealized_return"] = (
                            finite_or_none(values.mean())
                            if not values.empty
                            else None
                        )
                    rows.append(row)
    return rows


def _distribution(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return {
            "mean": None,
            "p25": None,
            "median": None,
            "p75": None,
        }
    return {
        "mean": finite_or_none(values.mean()),
        "p25": finite_or_none(values.quantile(0.25)),
        "median": finite_or_none(values.median()),
        "p75": finite_or_none(values.quantile(0.75)),
    }


def capacity_quality_frames(
    data: DiagnosticData,
    universe_id: str,
) -> pd.DataFrame:
    outcome_columns = [
        "code",
        "signal_date",
        "shadow_status",
        "exit_date",
        "holding_sessions",
        "mfe",
        "mae",
        "horizon_10",
        "horizon_20",
        "horizon_40",
        "horizon_60",
        "is_closed",
        "net_return_pct",
        "exit_reason",
        "normalized_exit_reason",
        "negative_exit_burden",
    ]
    result = data.decisions[universe_id].merge(
        data.shadows[universe_id][outcome_columns],
        on=["code", "signal_date"],
        how="left",
        validate="one_to_one",
    )
    result["ticker"] = result["code"]
    return result


def capacity_attribution_rows(data: DiagnosticData) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for universe_id in PRIMARY_UNIVERSES:
        quality = capacity_quality_frames(data, universe_id)
        for split in SPLIT_ORDER:
            signal_cohort = signal_in_split(
                quality,
                _bounds(data.context, split),
            )
            current_split = split_contained(
                quality,
                _bounds(data.context, split),
            )
            accepted_binding = current_split.loc[
                (current_split["disposition"] == "accepted")
                & current_split["capacity_binding_session"].astype(bool)
            ]
            rejected = current_split.loc[
                current_split["disposition"] == "capacity_rejected"
            ]
            comparison = cluster_bootstrap_difference(
                rejected,
                accepted_binding,
                label=f"capacity:{universe_id}:{split}",
            )
            observed_difference = comparison["observed_expectancy_difference"]
            if comparison["direction_stable"] and observed_difference is not None:
                priority_effect = (
                    "REJECTED_BETTER"
                    if float(observed_difference) > 0
                    else "ACCEPTED_BETTER"
                )
            else:
                priority_effect = "NOT_ROBUST"
            selectors = {
                "accepted_all": current_split["disposition"] == "accepted",
                "accepted_binding": (
                    (current_split["disposition"] == "accepted")
                    & current_split["capacity_binding_session"].astype(bool)
                ),
                "capacity_rejected": (
                    current_split["disposition"] == "capacity_rejected"
                ),
                "duplicate_rejected": (
                    current_split["disposition"] == "duplicate_rejected"
                ),
                "missing_next_session": (
                    current_split["disposition"] == "missing_next_session"
                ),
                "invalid_bar": (
                    current_split["disposition"] == "invalid_bar"
                ),
            }
            cohort_selectors = {
                "accepted_all": signal_cohort["disposition"] == "accepted",
                "accepted_binding": (
                    (signal_cohort["disposition"] == "accepted")
                    & signal_cohort["capacity_binding_session"].astype(bool)
                ),
                "capacity_rejected": (
                    signal_cohort["disposition"] == "capacity_rejected"
                ),
                "duplicate_rejected": (
                    signal_cohort["disposition"] == "duplicate_rejected"
                ),
                "missing_next_session": (
                    signal_cohort["disposition"] == "missing_next_session"
                ),
                "invalid_bar": (
                    signal_cohort["disposition"] == "invalid_bar"
                ),
            }
            for disposition_row in DISPOSITION_ROWS:
                quality_current = current_split.loc[selectors[disposition_row]]
                cohort_current = signal_cohort.loc[
                    cohort_selectors[disposition_row]
                ]
                count_only = disposition_row not in (
                    "accepted_all",
                    "accepted_binding",
                    "capacity_rejected",
                )
                metrics = clean_metrics(quality_current)
                if count_only:
                    metrics = {
                        key: (
                            "COUNT_ONLY"
                            if key == "sample_status"
                            else (
                                int(len(cohort_current))
                                if key == "trade_count"
                                else None
                            )
                        )
                        for key in metrics
                    }
                distribution_frame = cohort_current
                score = _distribution(distribution_frame, "score")
                liquidity = _distribution(
                    distribution_frame, "median_va_60"
                )
                sector = concentration(distribution_frame, "sector")
                rows.append(
                    {
                        "universe_id": universe_id,
                        "split": split,
                        "disposition_group": disposition_row,
                        "signal_count": int(len(cohort_current)),
                        "contained_quality_count": int(len(quality_current)),
                        "cross_boundary_or_censored_count": int(
                            len(cohort_current) - len(quality_current)
                        ),
                        "capacity_binding_session_count": int(
                                signal_cohort.loc[
                                signal_cohort[
                                    "capacity_binding_session"
                                ].astype(bool),
                                "entry_date",
                            ].nunique()
                        ),
                        "quality_scope": (
                            "FROZEN_ONE_SHOT"
                            if not count_only
                            else "COUNT_ONLY"
                        ),
                        "attribute_distribution_scope": "SIGNAL_COHORT",
                        **metrics,
                        "score_mean": score["mean"],
                        "score_p25": score["p25"],
                        "score_median": score["median"],
                        "score_p75": score["p75"],
                        "liquidity_mean": liquidity["mean"],
                        "liquidity_p25": liquidity["p25"],
                        "liquidity_median": liquidity["median"],
                        "liquidity_p75": liquidity["p75"],
                        "sector_distinct_count": sector["distinct_bucket_count"],
                        "sector_top_signal_share": sector["top_bucket_share"],
                        "sector_signal_hhi": sector["hhi"],
                        "score_90_share": (
                            finite_or_none(
                                (
                                    pd.to_numeric(
                                        distribution_frame["score"]
                                    )
                                    == 90
                                ).mean()
                            )
                            if not distribution_frame.empty
                            else None
                        ),
                        "score_100_share": (
                            finite_or_none(
                                (
                                    pd.to_numeric(
                                        distribution_frame["score"]
                                    )
                                    == 100
                                ).mean()
                            )
                            if not distribution_frame.empty
                            else None
                        ),
                        "score_120_share": (
                            finite_or_none(
                                (
                                    pd.to_numeric(
                                        distribution_frame["score"]
                                    )
                                    == 120
                                ).mean()
                            )
                            if not distribution_frame.empty
                            else None
                        ),
                        "rejected_minus_binding_accepted_expectancy": (
                            comparison["observed_expectancy_difference"]
                        ),
                        "comparison_ci_low": comparison["ci_low"],
                        "comparison_ci_high": comparison["ci_high"],
                        "comparison_same_direction_fraction": comparison[
                            "same_direction_fraction"
                        ],
                        "comparison_status": comparison["status"],
                        "priority_quality_effect": priority_effect,
                    }
                )
    return rows


def _anchored_curve(
    curve: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    dates = pd.to_datetime(curve["date"])
    prior = curve.loc[dates < start].tail(1)
    current = curve.loc[(dates >= start) & (dates <= end)]
    return pd.concat([prior, current], ignore_index=True)


def regime_summary_rows(data: DiagnosticData) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for universe_id in PRIMARY_UNIVERSES:
        daily = data.regime_daily[universe_id]
        ledger = data.accepted[universe_id]
        curve = data.context.curves[universe_id]
        for split in SPLIT_ORDER:
            bounds = _bounds(data.context, split)
            start, end = pd.Timestamp(bounds["start"]), pd.Timestamp(bounds["end"])
            mask = (daily["date"] >= start) & (daily["date"] <= end)
            current = daily.loc[mask]
            contained = split_contained(ledger, bounds)
            closed = _closed(contained)
            metrics = clean_metrics(contained)
            ticker = concentration(closed, "code")
            sector = concentration(closed, "sector")
            exit_counts = closed["normalized_exit_reason"].value_counts()
            anchored = _anchored_curve(curve, start, end)
            closed_count = len(closed)
            rows.append(
                {
                    "universe_id": universe_id,
                    "split": split,
                    "start_session": start.date().isoformat(),
                    "end_session": end.date().isoformat(),
                    "session_count": int(len(current)),
                    "raw_signal_count": int(current["raw_signal_count"].sum()),
                    "raw_signal_frequency_per_100_sessions": (
                        finite_or_none(
                            100.0 * current["raw_signal_count"].sum() / len(current)
                        )
                        if len(current)
                        else None
                    ),
                    "accepted_entry_count": int(
                        current["accepted_count"].sum()
                    ),
                    "capacity_rejection_count": int(
                        current["capacity_rejected_count"].sum()
                    ),
                    "duplicate_rejection_count": int(
                        current["duplicate_rejected_count"].sum()
                    ),
                    "capacity_rejection_share_of_nonduplicate_candidates": (
                        finite_or_none(
                            current["capacity_rejected_count"].sum()
                            / (
                                current["accepted_count"].sum()
                                + current["capacity_rejected_count"].sum()
                            )
                        )
                        if (
                            current["accepted_count"].sum()
                            + current["capacity_rejected_count"].sum()
                        )
                        else None
                    ),
                    "mean_active_member_count": _mean(
                        current, "active_member_count"
                    ),
                    "mean_active_member_weekly_above_200ma_share": _mean(
                        current,
                        "active_member_weekly_above_200ma_share",
                    ),
                    "mean_active_member_macd_uptrend_share": _mean(
                        current,
                        "active_member_macd_uptrend_share",
                    ),
                    "mean_cross_sectional_median_adjusted_return": _mean(
                        current,
                        "cross_sectional_median_adjusted_return",
                    ),
                    "mean_cross_sectional_adjusted_return_population_std": _mean(
                        current,
                        "cross_sectional_adjusted_return_population_std",
                    ),
                    "mean_signal_breadth": _mean(current, "signal_breadth"),
                    "mean_cash_utilization": _mean(
                        current, "cash_utilization"
                    ),
                    "maximum_cash_utilization": finite_or_none(
                        pd.to_numeric(
                            current["cash_utilization"], errors="coerce"
                        ).max()
                    ),
                    "mean_active_positions": _mean(current, "active_positions"),
                    "maximum_active_positions": finite_or_none(
                        pd.to_numeric(
                            current["active_positions"], errors="coerce"
                        ).max()
                    ),
                    "market_exposure_share": finite_or_none(
                        (pd.to_numeric(current["active_positions"]) > 0).mean()
                    ),
                    "maximum_drawdown": maximum_drawdown_for_window(anchored),
                    "closed_trade_count": closed_count,
                    "profit_factor": metrics["profit_factor"],
                    "expectancy_per_trade": metrics["expectancy_per_trade"],
                    "win_rate": metrics["win_rate"],
                    "average_holding_sessions": metrics[
                        "average_holding_sessions"
                    ],
                    "stop_family_exit_share": (
                        finite_or_none(
                            (
                                int(exit_counts.get("stop_loss", 0))
                                + int(exit_counts.get("stop_gap", 0))
                            )
                            / closed_count
                        )
                        if closed_count
                        else None
                    ),
                    "max_holding_exit_share": (
                        finite_or_none(
                            int(exit_counts.get("max_holding", 0))
                            / closed_count
                        )
                        if closed_count
                        else None
                    ),
                    "ticker_distinct_count": ticker["distinct_bucket_count"],
                    "ticker_top_trade_share": ticker["top_bucket_share"],
                    "ticker_trade_hhi": ticker["hhi"],
                    "sector_distinct_count": sector["distinct_bucket_count"],
                    "sector_top_trade_share": sector["top_bucket_share"],
                    "sector_trade_hhi": sector["hhi"],
                }
            )
    return rows


def _anonymous_net_attribution(
    pnl: pd.DataFrame,
    column: str,
) -> dict[str, Any]:
    if pnl.empty:
        return {
            "distinct_adverse_net_bucket_count": 0,
            "top_adverse_net_share": None,
            "top3_adverse_net_share": None,
            "adverse_net_hhi": None,
        }
    grouped = pnl.groupby(column, dropna=False)["pnl_jpy"].sum()
    adverse = (-grouped.loc[grouped < 0]).sort_values(ascending=False)
    if adverse.empty or float(adverse.sum()) <= 0:
        return {
            "distinct_adverse_net_bucket_count": 0,
            "top_adverse_net_share": None,
            "top3_adverse_net_share": None,
            "adverse_net_hhi": None,
        }
    shares = adverse / float(adverse.sum())
    return {
        "distinct_adverse_net_bucket_count": int(len(shares)),
        "top_adverse_net_share": finite_or_none(shares.iloc[0]),
        "top3_adverse_net_share": finite_or_none(shares.iloc[:3].sum()),
        "adverse_net_hhi": finite_or_none((shares**2).sum()),
    }


def drawdown_episode_rows(data: DiagnosticData) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    episode_count = int(
        CONTRACT["drawdown_diagnostic"]["episode_count_per_universe"]
    )
    for universe_id in PRIMARY_UNIVERSES:
        curve = data.context.curves[universe_id]
        pnl = data.position_pnl[universe_id]
        daily = data.regime_daily[universe_id]
        decisions = data.decisions[universe_id]
        episodes = drawdown_episodes(curve)[:episode_count]
        for rank, episode in enumerate(episodes, start=1):
            start = pd.Timestamp(episode["start_date"])
            trough = pd.Timestamp(episode["trough_date"])
            window_pnl = pnl.loc[
                (pnl["date"] > start) & (pnl["date"] <= trough)
            ]
            total_position_pnl = float(
                pd.to_numeric(window_pnl["pnl_jpy"], errors="coerce").sum()
            )
            curve_change = float(episode["equity_change_peak_to_trough"])
            if not np.isclose(
                total_position_pnl,
                curve_change,
                rtol=1e-10,
                atol=1e-5,
            ):
                raise RuntimeError(
                    f"{universe_id} drawdown episode PnL does not reconcile"
                )
            window_daily = daily.loc[
                (daily["date"] > start) & (daily["date"] <= trough)
            ]
            window_decisions = decisions.loc[
                pd.to_datetime(decisions["entry_date"]).gt(start)
                & pd.to_datetime(decisions["entry_date"]).le(trough)
            ]
            ticker_loss = anonymous_loss_attribution(
                window_pnl, "code"
            )
            sector_loss = anonymous_loss_attribution(
                window_pnl, "sector"
            )
            ticker_net = _anonymous_net_attribution(window_pnl, "code")
            sector_net = _anonymous_net_attribution(window_pnl, "sector")
            score_loss = categorical_loss_shares(
                window_pnl,
                "score",
                [90, 100, 120],
            )
            exit_loss = categorical_loss_shares(
                window_pnl,
                "trade_exit_reason",
                list(EXIT_REASONS),
            )
            gross_negative = float(
                -pd.to_numeric(
                    window_pnl.loc[
                        pd.to_numeric(window_pnl["pnl_jpy"]) < 0,
                        "pnl_jpy",
                    ],
                    errors="coerce",
                ).sum()
            )
            rows.append(
                {
                    "universe_id": universe_id,
                    "episode_rank": rank,
                    "start_date": start.date().isoformat(),
                    "trough_date": trough.date().isoformat(),
                    "recovery_date": (
                        pd.Timestamp(episode["recovery_date"]).date().isoformat()
                        if episode["recovery_date"] is not None
                        else None
                    ),
                    "drawdown": finite_or_none(episode["drawdown"]),
                    "peak_to_trough_equity_change_jpy": curve_change,
                    "position_net_pnl_jpy": total_position_pnl,
                    "position_pnl_reconciled": True,
                    "gross_negative_position_day_pnl_jpy": gross_negative,
                    "window_session_count": int(len(window_daily)),
                    "mean_active_positions": _mean(
                        window_daily, "active_positions"
                    ),
                    "maximum_active_positions": finite_or_none(
                        pd.to_numeric(
                            window_daily["active_positions"], errors="coerce"
                        ).max()
                    ),
                    "mean_cash_utilization": _mean(
                        window_daily, "cash_utilization"
                    ),
                    "maximum_cash_utilization": finite_or_none(
                        pd.to_numeric(
                            window_daily["cash_utilization"], errors="coerce"
                        ).max()
                    ),
                    "capacity_rejection_count": int(
                        (
                            window_decisions["disposition"]
                            == "capacity_rejected"
                        ).sum()
                    ),
                    "raw_signal_count": int(
                        window_daily["raw_signal_count"].sum()
                    ),
                    "raw_signal_frequency_per_100_sessions": (
                        finite_or_none(
                            100.0
                            * window_daily["raw_signal_count"].sum()
                            / len(window_daily)
                        )
                        if len(window_daily)
                        else None
                    ),
                    "mean_active_member_weekly_above_200ma_share": _mean(
                        window_daily,
                        "active_member_weekly_above_200ma_share",
                    ),
                    "mean_active_member_macd_uptrend_share": _mean(
                        window_daily,
                        "active_member_macd_uptrend_share",
                    ),
                    "mean_cross_sectional_median_adjusted_return": _mean(
                        window_daily,
                        "cross_sectional_median_adjusted_return",
                    ),
                    "mean_cross_sectional_adjusted_return_population_std": _mean(
                        window_daily,
                        "cross_sectional_adjusted_return_population_std",
                    ),
                    "mean_signal_breadth": _mean(
                        window_daily, "signal_breadth"
                    ),
                    "ticker_gross_loss_distinct_count": ticker_loss[
                        "distinct_loss_bucket_count"
                    ],
                    "ticker_gross_loss_top_share": ticker_loss["top_loss_share"],
                    "ticker_gross_loss_top3_share": ticker_loss[
                        "top3_loss_share"
                    ],
                    "ticker_gross_loss_hhi": ticker_loss["loss_hhi"],
                    "sector_gross_loss_distinct_count": sector_loss[
                        "distinct_loss_bucket_count"
                    ],
                    "sector_gross_loss_top_share": sector_loss["top_loss_share"],
                    "sector_gross_loss_top3_share": sector_loss[
                        "top3_loss_share"
                    ],
                    "sector_gross_loss_hhi": sector_loss["loss_hhi"],
                    "ticker_adverse_net_distinct_count": ticker_net[
                        "distinct_adverse_net_bucket_count"
                    ],
                    "ticker_adverse_net_top_share": ticker_net[
                        "top_adverse_net_share"
                    ],
                    "ticker_adverse_net_top3_share": ticker_net[
                        "top3_adverse_net_share"
                    ],
                    "ticker_adverse_net_hhi": ticker_net["adverse_net_hhi"],
                    "sector_adverse_net_distinct_count": sector_net[
                        "distinct_adverse_net_bucket_count"
                    ],
                    "sector_adverse_net_top_share": sector_net[
                        "top_adverse_net_share"
                    ],
                    "sector_adverse_net_top3_share": sector_net[
                        "top3_adverse_net_share"
                    ],
                    "sector_adverse_net_hhi": sector_net["adverse_net_hhi"],
                    "score_90_gross_loss_share": score_loss["90"],
                    "score_100_gross_loss_share": score_loss["100"],
                    "score_120_gross_loss_share": score_loss["120"],
                    **{
                        f"{reason}_gross_loss_share": exit_loss[str(reason)]
                        for reason in EXIT_REASONS
                    },
                }
            )
    return rows
