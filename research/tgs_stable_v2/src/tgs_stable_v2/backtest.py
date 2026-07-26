from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

import pandas as pd

from .config import CostScenario, MAX_HOLDING_DAYS, STOP_LOSS_PCT, TAKE_PROFIT_PCT


PathPolicy = Literal["conservative", "optimistic"]


@dataclass
class Trade:
    trade_id: str
    model_id: str
    universe_id: str
    ticker: str
    name: str
    sector: str
    signal_date: str
    score: int
    entry_date: str
    entry_raw_open: float
    entry_fill_price: float
    stop_price: float
    take_profit_price: float
    exit_date: str
    exit_raw_price: float
    exit_fill_price: float
    exit_reason: str
    holding_sessions: int
    gross_return_pct: float
    net_return_pct: float
    entry_cost_pct: float
    exit_cost_pct: float
    total_cost_pct: float
    cost_scenario: str
    path_policy: str
    is_closed: bool
    data_quality_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _net_return(
    entry_fill: float,
    exit_fill: float,
    commission_rate: float,
) -> tuple[float, float, float, float]:
    entry_cash = entry_fill * (1.0 + commission_rate)
    exit_cash = exit_fill * (1.0 - commission_rate)
    net = exit_cash / entry_cash - 1.0
    entry_cost_pct = commission_rate
    exit_cost_pct = commission_rate
    total_cost_pct = 2.0 * commission_rate
    return net, entry_cost_pct, exit_cost_pct, total_cost_pct


def _resolve_exit(
    row: pd.Series,
    *,
    stop_price: float,
    take_profit_price: float,
    holding_sessions: int,
    path_policy: PathPolicy,
) -> tuple[str, float] | None:
    raw_open = float(row["Open"])
    raw_high = float(row["High"])
    raw_low = float(row["Low"])
    raw_close = float(row["Close"])

    if raw_open <= stop_price:
        return "stop_gap", raw_open
    if raw_open >= take_profit_price:
        return "take_profit_gap", raw_open

    stop_hit = raw_low <= stop_price
    take_hit = raw_high >= take_profit_price
    if stop_hit and take_hit:
        if path_policy == "conservative":
            return "stop_and_take_same_day_stop_first", stop_price
        return "stop_and_take_same_day_take_first", take_profit_price
    if stop_hit:
        return "stop_loss", stop_price
    if take_hit:
        return "take_profit", take_profit_price
    if holding_sessions >= MAX_HOLDING_DAYS:
        return "max_holding", raw_close
    return None


def raw_signal_events(
    signal_frames: dict[str, pd.DataFrame],
    metadata: dict[str, dict[str, str]],
    *,
    evaluation_start: pd.Timestamp,
    evaluation_end: pd.Timestamp,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for ticker, frame in sorted(signal_frames.items()):
        selected = frame.loc[
            (frame.index >= evaluation_start)
            & (frame.index <= evaluation_end)
            & frame["indicator_ready"]
            & frame["entry_signal"]
        ]
        meta = metadata.get(ticker, {})
        for signal_date, row in selected.iterrows():
            rows.append(
                {
                    "universe_id": "U15",
                    "ticker": ticker,
                    "name": meta.get("name", ""),
                    "sector": meta.get("sector", ""),
                    "signal_date": signal_date.date().isoformat(),
                    "score": int(row["tgs_score"]),
                }
            )
    columns = ["universe_id", "ticker", "name", "sector", "signal_date", "score"]
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["signal_date", "ticker"],
        ignore_index=True,
    )


def simulate_ticker(
    ticker: str,
    frame: pd.DataFrame,
    metadata: dict[str, str],
    *,
    model_id: str,
    universe_id: str,
    evaluation_start: pd.Timestamp,
    evaluation_end: pd.Timestamp,
    market_dates: pd.DatetimeIndex,
    cost: CostScenario,
    path_policy: PathPolicy,
) -> tuple[list[Trade], dict[str, int]]:
    eligible = frame.loc[
        (frame.index >= evaluation_start)
        & (frame.index <= evaluation_end)
        & frame["indicator_ready"]
        & frame["entry_signal"]
    ]
    signal_dates = list(eligible.index)
    trades: list[Trade] = []
    counters = {
        "raw_signals": len(signal_dates),
        "signals_skipped_while_open": 0,
        "signals_unfilled_missing_next_session": 0,
        "signals_unfilled_at_data_end": 0,
    }
    signal_cursor = 0
    trade_sequence = 0

    while signal_cursor < len(signal_dates):
        signal_date = pd.Timestamp(signal_dates[signal_cursor])
        market_position = int(market_dates.searchsorted(signal_date, side="right"))
        if market_position >= len(market_dates):
            counters["signals_unfilled_at_data_end"] += 1
            signal_cursor += 1
            continue
        expected_entry_date = pd.Timestamp(market_dates[market_position])
        if expected_entry_date > evaluation_end:
            counters["signals_unfilled_at_data_end"] += 1
            signal_cursor += 1
            continue
        if expected_entry_date not in frame.index:
            counters["signals_unfilled_missing_next_session"] += 1
            signal_cursor += 1
            continue

        entry_index = int(frame.index.get_loc(expected_entry_date))
        entry_row = frame.iloc[entry_index]
        entry_raw_open = float(entry_row["Open"])
        if (
            entry_raw_open <= 0
            or float(entry_row["High"]) <= 0
            or float(entry_row["Low"]) <= 0
            or float(entry_row["Close"]) <= 0
            or float(entry_row["Volume"]) <= 0
        ):
            counters["signals_unfilled_missing_next_session"] += 1
            signal_cursor += 1
            continue

        trade_sequence += 1
        entry_fill = entry_raw_open * (1.0 + cost.slippage_rate)
        stop_price = entry_fill * (1.0 + STOP_LOSS_PCT)
        take_profit_price = entry_fill * (1.0 + TAKE_PROFIT_PCT)
        exit_index: int | None = None
        exit_reason = "open_at_data_end"
        exit_raw_price = float(frame.iloc[-1]["Close"])
        holding_sessions = 0

        for candidate_index in range(entry_index, len(frame)):
            candidate_date = pd.Timestamp(frame.index[candidate_index])
            if candidate_date > evaluation_end:
                break
            candidate_row = frame.iloc[candidate_index]
            if (
                float(candidate_row["Open"]) <= 0
                or float(candidate_row["High"]) <= 0
                or float(candidate_row["Low"]) <= 0
                or float(candidate_row["Close"]) <= 0
                or float(candidate_row["Volume"]) <= 0
            ):
                continue
            holding_sessions += 1
            resolution = _resolve_exit(
                candidate_row,
                stop_price=stop_price,
                take_profit_price=take_profit_price,
                holding_sessions=holding_sessions,
                path_policy=path_policy,
            )
            if resolution is not None:
                exit_reason, exit_raw_price = resolution
                exit_index = candidate_index
                break

        is_closed = exit_index is not None
        if is_closed:
            final_index = int(exit_index)
            final_date = pd.Timestamp(frame.index[final_index])
            data_quality_status = "complete"
        else:
            available = frame.loc[
                (frame.index >= expected_entry_date) & (frame.index <= evaluation_end)
            ].copy()
            available = available.loc[
                (available[["Open", "High", "Low", "Close"]] > 0).all(axis=1)
                & (available["Volume"] > 0)
            ]
            if available.empty:
                counters["signals_unfilled_at_data_end"] += 1
                signal_cursor += 1
                continue
            final_date = pd.Timestamp(available.index[-1])
            exit_raw_price = float(available.iloc[-1]["Close"])
            holding_sessions = len(available)
            final_index = int(frame.index.get_loc(final_date))
            data_quality_status = "right_censored_mark_to_market"

        exit_fill = exit_raw_price * (1.0 - cost.slippage_rate)
        net_return, entry_cost, exit_cost, total_cost = _net_return(
            entry_fill,
            exit_fill,
            cost.commission_rate,
        )
        gross_return = exit_raw_price / entry_raw_open - 1.0
        total_cost = gross_return - net_return
        trades.append(
            Trade(
                trade_id=f"{universe_id}-{ticker.replace('.', '')}-{trade_sequence:04d}",
                model_id=model_id,
                universe_id=universe_id,
                ticker=ticker,
                name=metadata.get("name", ""),
                sector=metadata.get("sector", ""),
                signal_date=signal_date.date().isoformat(),
                score=int(frame.loc[signal_date, "tgs_score"]),
                entry_date=expected_entry_date.date().isoformat(),
                entry_raw_open=entry_raw_open,
                entry_fill_price=entry_fill,
                stop_price=stop_price,
                take_profit_price=take_profit_price,
                exit_date=final_date.date().isoformat(),
                exit_raw_price=exit_raw_price,
                exit_fill_price=exit_fill,
                exit_reason=exit_reason,
                holding_sessions=holding_sessions,
                gross_return_pct=gross_return,
                net_return_pct=net_return,
                entry_cost_pct=entry_cost,
                exit_cost_pct=exit_cost,
                total_cost_pct=total_cost,
                cost_scenario=cost.name,
                path_policy=path_policy,
                is_closed=is_closed,
                data_quality_status=data_quality_status,
            )
        )

        next_signal_cursor = signal_cursor + 1
        while (
            next_signal_cursor < len(signal_dates)
            and pd.Timestamp(signal_dates[next_signal_cursor]) < final_date
        ):
            counters["signals_skipped_while_open"] += 1
            next_signal_cursor += 1
        signal_cursor = next_signal_cursor
        if not is_closed:
            counters["signals_skipped_while_open"] += len(signal_dates) - signal_cursor
            break

    return trades, counters


def simulate_universe(
    signal_frames: dict[str, pd.DataFrame],
    metadata: dict[str, dict[str, str]],
    *,
    model_id: str,
    universe_id: str,
    evaluation_start: pd.Timestamp,
    evaluation_end: pd.Timestamp,
    cost: CostScenario,
    path_policy: PathPolicy,
) -> tuple[pd.DataFrame, dict[str, int]]:
    market_dates = pd.DatetimeIndex(
        sorted(
            {
                pd.Timestamp(value)
                for frame in signal_frames.values()
                for value in frame.index
                if evaluation_start <= pd.Timestamp(value) <= evaluation_end
            }
        )
    )
    all_trades: list[dict[str, Any]] = []
    totals = {
        "raw_signals": 0,
        "signals_skipped_while_open": 0,
        "signals_unfilled_missing_next_session": 0,
        "signals_unfilled_at_data_end": 0,
    }
    for ticker, frame in sorted(signal_frames.items()):
        trades, counters = simulate_ticker(
            ticker,
            frame,
            metadata.get(ticker, {}),
            model_id=model_id,
            universe_id=universe_id,
            evaluation_start=evaluation_start,
            evaluation_end=evaluation_end,
            market_dates=market_dates,
            cost=cost,
            path_policy=path_policy,
        )
        all_trades.extend(trade.to_dict() for trade in trades)
        for key in totals:
            totals[key] += counters[key]

    columns = list(Trade.__dataclass_fields__)
    result = pd.DataFrame(all_trades, columns=columns)
    if not result.empty:
        result = result.sort_values(["signal_date", "ticker", "trade_id"], ignore_index=True)
    return result, totals
