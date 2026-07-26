from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0 or not math.isfinite(denominator):
        return None
    return numerator / denominator


def maximum_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    running_peak = equity.cummax()
    drawdown = equity / running_peak - 1.0
    return float(drawdown.min())


def cagr(equity: pd.Series) -> float | None:
    if len(equity) < 2 or equity.iloc[0] <= 0 or equity.iloc[-1] < 0:
        return None
    elapsed_days = (pd.Timestamp(equity.index[-1]) - pd.Timestamp(equity.index[0])).days
    if elapsed_days <= 0:
        return None
    years = elapsed_days / 365.2425
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0)


def max_consecutive_losses(returns: pd.Series) -> int:
    longest = 0
    current = 0
    for value in returns:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def trade_metrics(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty:
        closed = trades
    else:
        closed = trades.loc[trades["is_closed"].astype(bool)].copy()
    returns = pd.to_numeric(closed.get("net_return_pct", pd.Series(dtype=float)), errors="coerce").dropna()
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    profit_factor = _safe_ratio(gross_profit, gross_loss)
    average_win = float(wins.mean()) if not wins.empty else None
    average_loss = float(losses.mean()) if not losses.empty else None
    payoff_ratio = (
        _safe_ratio(average_win, abs(average_loss))
        if average_win is not None and average_loss is not None
        else None
    )
    holding = pd.to_numeric(closed.get("holding_sessions", pd.Series(dtype=float)), errors="coerce").dropna()
    ordered = closed.sort_values(["exit_date", "ticker"]) if not closed.empty else closed
    ordered_returns = pd.to_numeric(
        ordered.get("net_return_pct", pd.Series(dtype=float)),
        errors="coerce",
    ).dropna()
    return {
        "trade_count": int(len(trades)),
        "closed_trade_count": int(len(closed)),
        "open_trade_count": int(len(trades) - len(closed)),
        "win_rate": float((returns > 0).mean()) if not returns.empty else None,
        "average_win": average_win,
        "average_loss": average_loss,
        "payoff_ratio": payoff_ratio,
        "expectancy_per_trade": float(returns.mean()) if not returns.empty else None,
        "profit_factor": profit_factor,
        "max_consecutive_losses": max_consecutive_losses(ordered_returns),
        "average_holding_sessions": float(holding.mean()) if not holding.empty else None,
        "median_holding_sessions": float(holding.median()) if not holding.empty else None,
        "sum_net_returns": float(returns.sum()) if not returns.empty else 0.0,
    }


def concurrency_series(trades: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.Series:
    concurrency = pd.Series(0, index=dates, dtype=int)
    if trades.empty:
        return concurrency
    for row in trades.itertuples(index=False):
        entry = pd.Timestamp(row.entry_date)
        exit_date = pd.Timestamp(row.exit_date)
        concurrency.loc[(concurrency.index >= entry) & (concurrency.index <= exit_date)] += 1
    return concurrency


def equal_notional_equity(
    trades: pd.DataFrame,
    signal_frames: dict[str, pd.DataFrame],
    *,
    evaluation_start: pd.Timestamp,
    evaluation_end: pd.Timestamp,
) -> pd.DataFrame:
    """Build a no-selection, fixed equal-notional portfolio.

    One unit is assigned to every accepted independent trade. Initial capital
    equals the observed maximum simultaneous positions, so there is no
    leverage and no ex-post trade selection. Capital is not optimized or
    reinvested. Open-at-end trades are marked to the final available Close.
    """

    dates = pd.DatetimeIndex(
        sorted(
            {
                pd.Timestamp(value)
                for frame in signal_frames.values()
                for value in frame.index
                if evaluation_start <= pd.Timestamp(value) <= evaluation_end
            }
        )
    )
    if dates.empty:
        return pd.DataFrame(columns=["date", "equity", "active_positions", "exposure"])

    concurrency = concurrency_series(trades, dates)
    capacity = max(1, int(concurrency.max()))
    contribution = pd.Series(0.0, index=dates)

    for row in trades.itertuples(index=False):
        ticker_frame = signal_frames[row.ticker]
        entry = pd.Timestamp(row.entry_date)
        exit_date = pd.Timestamp(row.exit_date)
        entry_cash = float(row.entry_fill_price) * (1.0 + float(row.entry_cost_pct))
        active_dates = dates[(dates >= entry) & (dates <= exit_date)]
        for current_date in active_dates:
            if current_date == exit_date:
                value = float(row.exit_fill_price) * (1.0 - float(row.exit_cost_pct))
            elif current_date in ticker_frame.index:
                value = float(ticker_frame.loc[current_date, "Close"])
            else:
                prior = ticker_frame.loc[
                    (ticker_frame.index >= entry) & (ticker_frame.index <= current_date)
                ]
                if prior.empty:
                    continue
                value = float(prior.iloc[-1]["Close"])
            contribution.loc[current_date:] += (value / entry_cash - 1.0) / capacity
            # The contribution was added to all later dates; remove the prior
            # mark before applying the next mark for this trade.
            if current_date != active_dates[-1]:
                next_date = active_dates[active_dates.get_loc(current_date) + 1]
                contribution.loc[next_date:] -= (value / entry_cash - 1.0) / capacity

    equity = 1.0 + contribution
    return pd.DataFrame(
        {
            "date": dates,
            "equity": equity.values,
            "active_positions": concurrency.values,
            "capacity": capacity,
            "exposure": concurrency.values / capacity,
        }
    )


def portfolio_metrics(curve: pd.DataFrame) -> dict[str, Any]:
    if curve.empty:
        return {
            "total_return": None,
            "cagr": None,
            "maximum_drawdown": None,
            "calmar_ratio": None,
            "market_exposure": None,
            "maximum_concurrent_positions": 0,
        }
    equity = pd.Series(
        pd.to_numeric(curve["equity"], errors="coerce").values,
        index=pd.to_datetime(curve["date"]),
    ).dropna()
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    annualized = cagr(equity)
    max_dd = maximum_drawdown(equity)
    calmar = _safe_ratio(annualized, abs(max_dd)) if annualized is not None else None
    return {
        "total_return": total_return,
        "cagr": annualized,
        "maximum_drawdown": max_dd,
        "calmar_ratio": calmar,
        "market_exposure": float(pd.to_numeric(curve["exposure"]).mean()),
        "maximum_concurrent_positions": int(pd.to_numeric(curve["active_positions"]).max()),
    }


def longest_no_signal_period(
    signals: pd.DataFrame,
    market_dates: pd.DatetimeIndex,
) -> dict[str, Any]:
    if market_dates.empty:
        return {"sessions": 0, "calendar_days": 0, "start": None, "end": None}
    ordered_dates = pd.DatetimeIndex(sorted({pd.Timestamp(value) for value in market_dates}))
    signal_dates = {
        pd.Timestamp(value)
        for value in signals.get("signal_date", [])
        if pd.Timestamp(value) in ordered_dates
    }
    best = {"sessions": 0, "calendar_days": 0, "start": None, "end": None}
    run_start: pd.Timestamp | None = None

    def consider(start: pd.Timestamp | None, end: pd.Timestamp) -> None:
        nonlocal best
        if start is None:
            return
        sessions = int(((ordered_dates >= start) & (ordered_dates <= end)).sum())
        calendar_days = int((end - start).days + 1)
        if (sessions, calendar_days) > (best["sessions"], best["calendar_days"]):
            best = {
                "sessions": sessions,
                "calendar_days": calendar_days,
                "start": start.date().isoformat(),
                "end": end.date().isoformat(),
            }

    for position, current in enumerate(ordered_dates):
        if current not in signal_dates:
            if run_start is None:
                run_start = current
            if position == len(ordered_dates) - 1:
                consider(run_start, current)
            continue
        if run_start is not None:
            consider(run_start, ordered_dates[position - 1])
            run_start = None
    return best
