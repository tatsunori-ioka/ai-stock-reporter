from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping

import pandas as pd

from tgs_stable_v2.config import (
    MAX_HOLDING_DAYS,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    CostScenario,
)


PathPolicy = Literal["conservative", "optimistic"]
TerminalPolicy = Literal["haircut_20", "last_close"]


@dataclass
class Position:
    code: str
    sector: str
    signal_date: pd.Timestamp
    entry_date: pd.Timestamp
    score: int
    signal_median_va: float
    shares: float
    entry_raw_open: float
    entry_fill_price: float
    entry_cash_per_share: float
    stop_price: float
    take_price: float
    holding_sessions: int
    last_close: float
    last_bar_date: pd.Timestamp


def rank_candidates(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return frame.sort_values(
        ["score", "median_va_60", "code"],
        ascending=[False, False, True],
        kind="mergesort",
        ignore_index=True,
    )


def _valid_bar(row: pd.Series) -> bool:
    values = [row.get(key) for key in ("Open", "High", "Low", "Close", "Volume")]
    return all(pd.notna(value) and float(value) > 0 for value in values)


def _exit_price(
    row: pd.Series,
    position: Position,
    path_policy: PathPolicy,
    *,
    include_gap: bool,
) -> tuple[str, float] | None:
    raw_open = float(row["Open"])
    high = float(row["High"])
    low = float(row["Low"])
    close = float(row["Close"])
    if include_gap and raw_open <= position.stop_price:
        return "stop_gap", raw_open
    if include_gap and raw_open >= position.take_price:
        return "take_profit_gap", raw_open
    stop_hit = low <= position.stop_price
    take_hit = high >= position.take_price
    if stop_hit and take_hit:
        return (
            "stop_and_take_same_day_stop_first",
            position.stop_price,
        ) if path_policy == "conservative" else (
            "stop_and_take_same_day_take_first",
            position.take_price,
        )
    if stop_hit:
        return "stop_loss", position.stop_price
    if take_hit:
        return "take_profit", position.take_price
    if position.holding_sessions >= MAX_HOLDING_DAYS:
        return "max_holding", close
    return None


def _trade_row(
    position: Position,
    *,
    exit_date: pd.Timestamp,
    exit_raw_price: float,
    exit_fill_price: float,
    exit_reason: str,
    commission_rate: float,
    is_closed: bool,
    data_quality_status: str,
) -> dict[str, Any]:
    exit_cash = exit_fill_price * (1.0 - commission_rate)
    net_return = exit_cash / position.entry_cash_per_share - 1.0
    return {
        "code": position.code,
        "ticker": position.code,
        "sector": position.sector,
        "signal_date": position.signal_date.date().isoformat(),
        "entry_date": position.entry_date.date().isoformat(),
        "exit_date": exit_date.date().isoformat(),
        "last_observed_bar_date": position.last_bar_date.date().isoformat(),
        "score": position.score,
        "signal_median_va": position.signal_median_va,
        "shares": position.shares,
        "entry_raw_open": position.entry_raw_open,
        "entry_fill_price": position.entry_fill_price,
        "exit_raw_price": exit_raw_price,
        "exit_fill_price": exit_fill_price,
        "exit_reason": exit_reason,
        "holding_sessions": position.holding_sessions,
        "net_return_pct": net_return,
        "is_closed": is_closed,
        "data_quality_status": data_quality_status,
    }


def _mark(
    position: Position,
    session: pd.Timestamp,
    frames: Mapping[str, pd.DataFrame],
    *,
    field: str,
) -> float:
    frame = frames[position.code]
    if session in frame.index:
        row = frame.loc[session]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[-1]
        value = row.get(field)
        if pd.notna(value) and float(value) > 0:
            return float(value)
    return position.last_close


def simulate_capital_proxy(
    signals: pd.DataFrame,
    frames: Mapping[str, pd.DataFrame],
    sessions: pd.DatetimeIndex,
    *,
    cost: CostScenario,
    path_policy: PathPolicy,
    terminal_policy: TerminalPolicy,
    initial_capital: float = 10_000_000.0,
    maximum_positions: int = 10,
    maximum_position_fraction: float = 0.10,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    if initial_capital <= 0:
        raise ValueError("initial capital must be positive")
    commission = cost.commission_rate
    slippage = cost.slippage_rate
    signal_rows = signals.copy()
    signal_rows["signal_date"] = pd.to_datetime(signal_rows["signal_date"])
    entries: dict[pd.Timestamp, list[dict[str, Any]]] = {}
    counters = {
        "raw_signals": len(signal_rows),
        "accepted_entries": 0,
        "capacity_rejections": 0,
        "duplicate_rejections": 0,
        "missing_next_session_rejections": 0,
        "invalid_bar_rejections": 0,
        "premature_data_end_suspicions": 0,
    }
    session_set = set(sessions)
    for row in signal_rows.to_dict(orient="records"):
        signal_date = pd.Timestamp(row["signal_date"])
        next_position = int(sessions.searchsorted(signal_date, side="right"))
        if next_position >= len(sessions):
            counters["missing_next_session_rejections"] += 1
            continue
        entry_date = pd.Timestamp(sessions[next_position])
        entries.setdefault(entry_date, []).append(row)

    cash = float(initial_capital)
    positions: dict[str, Position] = {}
    ledger: list[dict[str, Any]] = []
    curve: list[dict[str, Any]] = [
        {
            "date": (pd.Timestamp(sessions[0]) - pd.Timedelta(days=1)).date().isoformat(),
            "equity": initial_capital,
            "cash": initial_capital,
            "active_positions": 0,
            "cash_utilization": 0.0,
        }
    ]

    for session in sessions:
        session = pd.Timestamp(session)
        gap_exited: set[str] = set()

        # Only exits knowable from the opening print may release Open capacity.
        for code in sorted(list(positions)):
            position = positions[code]
            frame = frames[code]
            if session not in frame.index:
                continue
            row = frame.loc[session]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[-1]
            if not _valid_bar(row):
                continue
            position.holding_sessions += 1
            position.last_close = float(row["Close"])
            position.last_bar_date = session
            resolution = _exit_price(
                row,
                position,
                path_policy,
                include_gap=True,
            )
            if resolution is None or not resolution[0].endswith("_gap"):
                continue
            reason, raw_exit = resolution
            fill = raw_exit * (1.0 - slippage)
            cash += position.shares * fill * (1.0 - commission)
            ledger.append(
                _trade_row(
                    position,
                    exit_date=session,
                    exit_raw_price=raw_exit,
                    exit_fill_price=fill,
                    exit_reason=reason,
                    commission_rate=commission,
                    is_closed=True,
                    data_quality_status="complete",
                )
            )
            gap_exited.add(code)
            del positions[code]

        open_market_value = sum(
            position.shares * _mark(position, session, frames, field="Open")
            for position in positions.values()
        )
        open_equity = cash + open_market_value

        candidates = rank_candidates(pd.DataFrame(entries.get(session, [])))
        for row in candidates.to_dict(orient="records"):
            code = str(row["code"])
            if code in positions:
                counters["duplicate_rejections"] += 1
                continue
            if len(positions) >= maximum_positions:
                counters["capacity_rejections"] += 1
                continue
            frame = frames.get(code)
            if frame is None or session not in frame.index:
                counters["missing_next_session_rejections"] += 1
                continue
            bar = frame.loc[session]
            if isinstance(bar, pd.DataFrame):
                bar = bar.iloc[-1]
            if not _valid_bar(bar):
                counters["invalid_bar_rejections"] += 1
                continue
            raw_open = float(bar["Open"])
            entry_fill = raw_open * (1.0 + slippage)
            cash_per_share = entry_fill * (1.0 + commission)
            budget = min(maximum_position_fraction * open_equity, cash)
            if budget <= 0 or cash_per_share <= 0:
                counters["capacity_rejections"] += 1
                continue
            shares = budget / cash_per_share
            cash -= shares * cash_per_share
            if cash < 0:
                if cash >= -1e-8:
                    cash = 0.0
                else:
                    raise RuntimeError("cash invariant violated after entry")
            positions[code] = Position(
                code=code,
                sector=str(row.get("sector", "")),
                signal_date=pd.Timestamp(row["signal_date"]),
                entry_date=session,
                score=int(row["score"]),
                signal_median_va=float(row.get("median_va_60", 0.0)),
                shares=shares,
                entry_raw_open=raw_open,
                entry_fill_price=entry_fill,
                entry_cash_per_share=cash_per_share,
                stop_price=entry_fill * (1.0 + STOP_LOSS_PCT),
                take_price=entry_fill * (1.0 + TAKE_PROFIT_PCT),
                holding_sessions=0,
                last_close=float(bar["Close"]),
                last_bar_date=session,
            )
            counters["accepted_entries"] += 1

        # Intraday and Close exits cannot retroactively fund this Open.
        for code in sorted(list(positions)):
            position = positions[code]
            frame = frames[code]
            if session not in frame.index:
                continue
            row = frame.loc[session]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[-1]
            if not _valid_bar(row):
                continue
            if position.entry_date == session:
                position.holding_sessions += 1
            position.last_close = float(row["Close"])
            position.last_bar_date = session
            resolution = _exit_price(
                row,
                position,
                path_policy,
                include_gap=False,
            )
            if resolution is None:
                continue
            reason, raw_exit = resolution
            fill = raw_exit * (1.0 - slippage)
            cash += position.shares * fill * (1.0 - commission)
            ledger.append(
                _trade_row(
                    position,
                    exit_date=session,
                    exit_raw_price=raw_exit,
                    exit_fill_price=fill,
                    exit_reason=reason,
                    commission_rate=commission,
                    is_closed=True,
                    data_quality_status="complete",
                )
            )
            del positions[code]

        # A signal emitted while the same ticker is still open at this
        # session's close cannot become a duplicate next-session order.
        next_position = int(sessions.searchsorted(session, side="right"))
        if next_position < len(sessions):
            next_session = pd.Timestamp(sessions[next_position])
            scheduled = entries.get(next_session, [])
            retained: list[dict[str, Any]] = []
            for candidate in scheduled:
                if (
                    pd.Timestamp(candidate["signal_date"]) == session
                    and str(candidate["code"]) in positions
                ):
                    counters["duplicate_rejections"] += 1
                    continue
                retained.append(candidate)
            entries[next_session] = retained

        market_value = sum(
            position.shares * _mark(position, session, frames, field="Close")
            for position in positions.values()
        )
        equity = cash + market_value
        curve.append(
            {
                "date": session.date().isoformat(),
                "equity": equity,
                "cash": cash,
                "active_positions": len(positions),
                "cash_utilization": market_value / equity if equity > 0 else None,
            }
        )

    evaluation_end = pd.Timestamp(sessions[-1])
    for code in sorted(list(positions)):
        position = positions[code]
        premature = position.last_bar_date < evaluation_end
        if premature:
            counters["premature_data_end_suspicions"] += 1
            raw_exit = position.last_close * (0.8 if terminal_policy == "haircut_20" else 1.0)
            fill = raw_exit * (1.0 - slippage)
            cash += position.shares * fill * (1.0 - commission)
            ledger.append(
                _trade_row(
                    position,
                    exit_date=evaluation_end,
                    exit_raw_price=raw_exit,
                    exit_fill_price=fill,
                    exit_reason=(
                        "premature_data_end_haircut"
                        if terminal_policy == "haircut_20"
                        else "premature_data_end_last_close"
                    ),
                    commission_rate=commission,
                    is_closed=True,
                    data_quality_status="premature_data_end_suspicion",
                )
            )
            del positions[code]
            continue
        fill = position.last_close
        ledger.append(
            _trade_row(
                position,
                exit_date=evaluation_end,
                exit_raw_price=fill,
                exit_fill_price=fill,
                exit_reason="open_at_frozen_end",
                commission_rate=commission,
                is_closed=False,
                data_quality_status="right_censored_mark_to_market",
            )
        )

    curve_frame = pd.DataFrame(curve)
    if counters["premature_data_end_suspicions"] and not curve_frame.empty:
        remaining_value = sum(
            position.shares * position.last_close for position in positions.values()
        )
        curve_frame.loc[curve_frame.index[-1], "cash"] = cash
        curve_frame.loc[curve_frame.index[-1], "equity"] = cash + remaining_value
        curve_frame.loc[curve_frame.index[-1], "active_positions"] = len(positions)
        final_equity = cash + remaining_value
        curve_frame.loc[curve_frame.index[-1], "cash_utilization"] = (
            remaining_value / final_equity if final_equity > 0 else None
        )
    ledger_frame = pd.DataFrame(ledger)
    if not ledger_frame.empty:
        ledger_frame = ledger_frame.sort_values(
            ["signal_date", "code", "entry_date"],
            ignore_index=True,
        )
    return ledger_frame, curve_frame, counters
