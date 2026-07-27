from __future__ import annotations

from typing import Mapping

import pandas as pd

from tgs_stable_v2.backtest import Trade, simulate_ticker
from tgs_stable_v2.config import CostScenario
from tgs_stable_v2.metrics import equal_notional_equity

from .contract import MODEL_ID


def independent_trades(
    universe_id: str,
    frames: Mapping[str, pd.DataFrame],
    sessions: pd.DatetimeIndex,
    *,
    evaluation_start: pd.Timestamp,
    evaluation_end: pd.Timestamp,
    cost: CostScenario,
    path_policy: str,
) -> tuple[pd.DataFrame, dict[str, int]]:
    rows: list[dict[str, object]] = []
    totals = {
        "raw_signals": 0,
        "signals_skipped_while_open": 0,
        "signals_unfilled_missing_next_session": 0,
        "signals_unfilled_at_data_end": 0,
    }
    for code, frame in sorted(frames.items()):
        trades, counters = simulate_ticker(
            code,
            frame,
            {},
            model_id=MODEL_ID,
            universe_id=universe_id,
            evaluation_start=evaluation_start,
            evaluation_end=evaluation_end,
            market_dates=sessions,
            cost=cost,
            path_policy=path_policy,  # type: ignore[arg-type]
        )
        rows.extend(trade.to_dict() for trade in trades)
        for key in totals:
            totals[key] += counters[key]
    result = pd.DataFrame(rows, columns=list(Trade.__dataclass_fields__))
    if not result.empty:
        result = result.sort_values(["signal_date", "ticker"], ignore_index=True)
    return result, totals


def equal_notional_curve(
    trades: pd.DataFrame,
    frames: Mapping[str, pd.DataFrame],
    *,
    evaluation_start: pd.Timestamp,
    evaluation_end: pd.Timestamp,
) -> pd.DataFrame:
    return equal_notional_equity(
        trades,
        dict(frames),
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
    )
