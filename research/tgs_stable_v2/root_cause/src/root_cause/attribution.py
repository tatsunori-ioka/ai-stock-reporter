from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from tgs_stable_v2.config import COST_SCENARIOS

from .data import DiagnosticContext
from .statistics import finite_or_none, normalize_exit_reason


def position_daily_pnl(
    context: DiagnosticContext,
    universe_id: str,
) -> pd.DataFrame:
    commission = COST_SCENARIOS["basic"].commission_rate
    rows: list[dict[str, Any]] = []
    for trade in context.ledgers[universe_id].itertuples(index=False):
        code = str(trade.code)
        frame = context.frames[universe_id][code]
        entry_date = pd.Timestamp(trade.entry_date)
        exit_date = pd.Timestamp(trade.exit_date)
        shares = float(trade.shares)
        prior_mark = float(trade.entry_fill_price) * (1.0 + commission)
        trade_exit_reason = normalize_exit_reason(trade.exit_reason)
        trade_sessions = context.sessions[
            (context.sessions >= entry_date) & (context.sessions <= exit_date)
        ]
        for session in trade_sessions:
            session = pd.Timestamp(session)
            is_closed_exit = session == exit_date and bool(trade.is_closed)
            if is_closed_exit:
                current_mark = float(trade.exit_fill_price) * (1.0 - commission)
                daily_event_reason = trade_exit_reason
            else:
                daily_event_reason = "mark_to_market"
                if session in frame.index:
                    bar = frame.loc[session]
                    if isinstance(bar, pd.DataFrame):
                        bar = bar.iloc[-1]
                    close = bar.get("Close")
                    if pd.notna(close) and float(close) > 0:
                        current_mark = float(close)
                    else:
                        current_mark = prior_mark
                else:
                    current_mark = prior_mark
            pnl = shares * (current_mark - prior_mark)
            rows.append(
                {
                    "date": session,
                    "code": code,
                    "sector": str(trade.sector),
                    "score": int(trade.score),
                    "trade_exit_reason": trade_exit_reason,
                    "daily_event_reason": daily_event_reason,
                    "pnl_jpy": float(pnl),
                }
            )
            prior_mark = current_mark
            if is_closed_exit:
                break
    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values(["date", "code"], ignore_index=True)
    return result


def verify_daily_pnl_reconciliation(
    context: DiagnosticContext,
    universe_id: str,
    pnl: pd.DataFrame,
) -> dict[str, Any]:
    curve = context.curves[universe_id].copy()
    curve["equity"] = pd.to_numeric(curve["equity"], errors="coerce")
    curve["curve_change"] = curve["equity"].diff()
    daily = pnl.groupby("date", as_index=False)["pnl_jpy"].sum()
    merged = curve.merge(daily, on="date", how="outer", indicator=True)
    if (merged["_merge"] == "right_only").any():
        raise RuntimeError(f"{universe_id} daily PnL contains an unknown curve date")
    merged = merged.sort_values("date", ignore_index=True)
    merged["pnl_jpy"] = merged["pnl_jpy"].fillna(0.0)
    comparable = merged["curve_change"].notna() & (merged["_merge"] == "both")
    errors = (
        merged.loc[comparable, "curve_change"]
        - merged.loc[comparable, "pnl_jpy"]
    ).abs()
    maximum = float(errors.max()) if not errors.empty else 0.0
    scale = float(curve["equity"].abs().max())
    tolerance = max(1e-5, scale * 1e-10)
    if maximum > tolerance:
        raise RuntimeError(
            f"{universe_id} daily PnL does not reconcile: "
            f"{maximum} > {tolerance}"
        )
    return {
        "maximum_absolute_reconciliation_error_jpy": maximum,
        "tolerance_jpy": tolerance,
        "match": True,
    }


def drawdown_episodes(curve: pd.DataFrame) -> list[dict[str, Any]]:
    ordered = curve.sort_values("date", ignore_index=True).copy()
    equity = pd.to_numeric(ordered["equity"], errors="coerce")
    if len(ordered) < 2 or equity.isna().any():
        raise RuntimeError("curve cannot support drawdown episodes")
    peak_index = 0
    active: dict[str, Any] | None = None
    episodes: list[dict[str, Any]] = []
    for index in range(1, len(ordered)):
        value = float(equity.iloc[index])
        peak_value = float(equity.iloc[peak_index])
        if active is None:
            if value >= peak_value:
                peak_index = index
                continue
            active = {
                "start_index": peak_index,
                "trough_index": index,
                "peak_equity": peak_value,
            }
            continue
        trough_index = int(active["trough_index"])
        if value < float(equity.iloc[trough_index]):
            active["trough_index"] = index
        if value >= float(active["peak_equity"]):
            active["recovery_index"] = index
            episodes.append(active)
            active = None
            peak_index = index
    if active is not None:
        active["recovery_index"] = None
        episodes.append(active)
    result: list[dict[str, Any]] = []
    for episode in episodes:
        start = int(episode["start_index"])
        trough = int(episode["trough_index"])
        recovery = episode["recovery_index"]
        peak = float(equity.iloc[start])
        trough_value = float(equity.iloc[trough])
        result.append(
            {
                **episode,
                "start_date": pd.Timestamp(ordered.iloc[start]["date"]),
                "trough_date": pd.Timestamp(ordered.iloc[trough]["date"]),
                "recovery_date": (
                    pd.Timestamp(ordered.iloc[int(recovery)]["date"])
                    if recovery is not None
                    else None
                ),
                "drawdown": trough_value / peak - 1.0,
                "equity_change_peak_to_trough": trough_value - peak,
            }
        )
    return sorted(
        result,
        key=lambda row: (
            float(row["drawdown"]),
            row["start_date"],
            row["trough_date"],
        ),
    )


def anonymous_loss_attribution(
    pnl: pd.DataFrame,
    column: str,
) -> dict[str, Any]:
    losses = pnl.loc[pd.to_numeric(pnl["pnl_jpy"]) < 0].copy()
    if losses.empty:
        return {
            "distinct_loss_bucket_count": 0,
            "top_loss_share": None,
            "top3_loss_share": None,
            "loss_hhi": None,
        }
    grouped = -losses.groupby(column, dropna=False)["pnl_jpy"].sum()
    grouped = grouped.loc[grouped > 0].sort_values(ascending=False)
    total = float(grouped.sum())
    shares = grouped / total
    return {
        "distinct_loss_bucket_count": int(len(shares)),
        "top_loss_share": finite_or_none(shares.iloc[0]),
        "top3_loss_share": finite_or_none(shares.iloc[:3].sum()),
        "loss_hhi": finite_or_none((shares**2).sum()),
    }


def categorical_loss_shares(
    pnl: pd.DataFrame,
    column: str,
    categories: list[Any],
) -> dict[str, float | None]:
    losses = pnl.loc[pd.to_numeric(pnl["pnl_jpy"]) < 0].copy()
    total = float(-pd.to_numeric(losses["pnl_jpy"]).sum())
    result: dict[str, float | None] = {}
    for category in categories:
        current = losses.loc[losses[column] == category]
        value = float(-pd.to_numeric(current["pnl_jpy"]).sum())
        result[str(category)] = finite_or_none(value / total) if total > 0 else None
    return result


def maximum_drawdown_for_window(curve: pd.DataFrame) -> float | None:
    if curve.empty:
        return None
    equity = pd.to_numeric(curve["equity"], errors="coerce").dropna()
    if equity.empty:
        return None
    drawdown = equity / equity.cummax() - 1.0
    return finite_or_none(drawdown.min())


def paired_month_bootstrap(
    left: pd.Series,
    right: pd.Series,
    *,
    seed: int,
    replicates: int,
) -> dict[str, Any]:
    paired = pd.concat(
        [left.rename("left"), right.rename("right")],
        axis=1,
        join="inner",
    ).dropna()
    if len(paired) < 12:
        return {
            "paired_months": int(len(paired)),
            "observed_difference": None,
            "ci_low": None,
            "ci_high": None,
            "same_direction_fraction": None,
            "direction_stable": False,
            "status": "INSUFFICIENT_SAMPLE",
        }
    values = paired["left"].to_numpy() - paired["right"].to_numpy()
    observed = float(values.mean())
    generator = np.random.default_rng(seed)
    indices = generator.integers(0, len(values), size=(replicates, len(values)))
    samples = values[indices].mean(axis=1)
    low, high = np.quantile(samples, [0.025, 0.975])
    direction = 1 if observed > 0 else -1
    same = float(np.mean(np.sign(samples) == direction))
    stable = same >= 0.95 and (
        (observed > 0 and low > 0) or (observed < 0 and high < 0)
    )
    return {
        "paired_months": int(len(paired)),
        "observed_difference": finite_or_none(observed),
        "ci_low": finite_or_none(low),
        "ci_high": finite_or_none(high),
        "same_direction_fraction": finite_or_none(same),
        "direction_stable": bool(stable),
        "status": "SUFFICIENT",
    }
