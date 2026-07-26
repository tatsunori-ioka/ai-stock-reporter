from __future__ import annotations

import pandas as pd
import pytest

from tgs_stable_v2.backtest import simulate_ticker
from tgs_stable_v2.config import COST_SCENARIOS, MODEL_ID


def frame_from_rows(rows: list[tuple[str, float, float, float, float]], signals: set[str]) -> pd.DataFrame:
    index = pd.to_datetime([row[0] for row in rows])
    frame = pd.DataFrame(
        {
            "Open": [row[1] for row in rows],
            "High": [row[2] for row in rows],
            "Low": [row[3] for row in rows],
            "Close": [row[4] for row in rows],
            "Volume": 1_000_000,
            "indicator_ready": True,
            "entry_signal": [row[0] in signals for row in rows],
            "tgs_score": [90 if row[0] in signals else 0 for row in rows],
        },
        index=index,
    )
    return frame


def run(
    frame: pd.DataFrame,
    *,
    path_policy: str = "conservative",
    cost_name: str = "zero",
    market_dates: pd.DatetimeIndex | None = None,
):
    return simulate_ticker(
        "TEST.T",
        frame,
        {"name": "Test", "sector": "Test sector"},
        model_id=MODEL_ID,
        universe_id="U15",
        evaluation_start=frame.index.min(),
        evaluation_end=frame.index.max(),
        market_dates=market_dates if market_dates is not None else frame.index,
        cost=COST_SCENARIOS[cost_name],
        path_policy=path_policy,
    )


def test_entry_is_next_session_open_not_signal_close() -> None:
    frame = frame_from_rows(
        [
            ("2024-01-02", 95, 101, 94, 100),
            ("2024-01-03", 110, 111, 109, 110),
            ("2024-01-04", 111, 112, 110, 111),
        ],
        {"2024-01-02"},
    )
    trades, _ = run(frame)
    assert trades[0].signal_date == "2024-01-02"
    assert trades[0].entry_date == "2024-01-03"
    assert trades[0].entry_raw_open == 110
    assert trades[0].entry_raw_open != frame.loc["2024-01-02", "Close"]


def test_stop_gap_fills_at_open() -> None:
    frame = frame_from_rows(
        [
            ("2024-01-02", 100, 101, 99, 100),
            ("2024-01-03", 100, 105, 95, 100),
            ("2024-01-04", 85, 90, 80, 86),
        ],
        {"2024-01-02"},
    )
    trades, _ = run(frame)
    assert trades[0].exit_reason == "stop_gap"
    assert trades[0].exit_raw_price == 85


def test_take_profit_gap_fills_at_open() -> None:
    frame = frame_from_rows(
        [
            ("2024-01-02", 100, 101, 99, 100),
            ("2024-01-03", 100, 105, 95, 100),
            ("2024-01-04", 135, 140, 134, 138),
        ],
        {"2024-01-02"},
    )
    trades, _ = run(frame)
    assert trades[0].exit_reason == "take_profit_gap"
    assert trades[0].exit_raw_price == 135


def test_same_bar_conservative_and_optimistic_paths() -> None:
    frame = frame_from_rows(
        [
            ("2024-01-02", 100, 101, 99, 100),
            ("2024-01-03", 100, 135, 85, 100),
        ],
        {"2024-01-02"},
    )
    conservative, _ = run(frame, path_policy="conservative")
    optimistic, _ = run(frame, path_policy="optimistic")
    assert conservative[0].exit_raw_price == 90
    assert conservative[0].exit_reason.endswith("stop_first")
    assert optimistic[0].exit_raw_price == 130
    assert optimistic[0].exit_reason.endswith("take_first")


def test_max_holding_exits_on_60th_entry_inclusive_session_close() -> None:
    dates = pd.bdate_range("2024-01-02", periods=61)
    rows = [(date.date().isoformat(), 100, 105, 95, 101) for date in dates]
    frame = frame_from_rows(rows, {dates[0].date().isoformat()})
    trades, _ = run(frame)
    assert trades[0].holding_sessions == 60
    assert trades[0].entry_date == dates[1].date().isoformat()
    assert trades[0].exit_date == dates[60].date().isoformat()
    assert trades[0].exit_reason == "max_holding"
    assert trades[0].exit_raw_price == 101


def test_stop_or_take_on_60th_session_precedes_max_holding_close() -> None:
    dates = pd.bdate_range("2024-01-02", periods=61)
    rows = [(date.date().isoformat(), 100, 105, 95, 101) for date in dates]
    rows[-1] = (dates[-1].date().isoformat(), 100, 131, 95, 101)
    frame = frame_from_rows(rows, {dates[0].date().isoformat()})
    trades, _ = run(frame)
    assert trades[0].holding_sessions == 60
    assert trades[0].exit_reason == "take_profit"
    assert trades[0].exit_raw_price == 130


def test_zero_volume_row_while_held_is_not_a_holding_session() -> None:
    dates = pd.bdate_range("2024-01-02", periods=62)
    rows = [(date.date().isoformat(), 100, 105, 95, 101) for date in dates]
    frame = frame_from_rows(rows, {dates[0].date().isoformat()})
    frame.loc[dates[2], "Volume"] = 0
    trades, _ = run(frame)
    assert trades[0].holding_sessions == 60
    assert trades[0].exit_date == dates[-1].date().isoformat()
    assert trades[0].exit_reason == "max_holding"


def test_overlapping_same_ticker_signals_are_skipped() -> None:
    dates = pd.bdate_range("2024-01-02", periods=20)
    rows = [(date.date().isoformat(), 100, 105, 95, 100) for date in dates]
    signals = {date.date().isoformat() for date in dates[:-1]}
    trades, counters = run(frame_from_rows(rows, signals))
    assert len(trades) == 1
    assert counters["signals_skipped_while_open"] == len(signals) - 1


def test_missing_immediate_market_session_is_unfilled() -> None:
    frame = frame_from_rows(
        [
            ("2024-01-02", 100, 101, 99, 100),
            ("2024-01-04", 100, 101, 99, 100),
        ],
        {"2024-01-02"},
    )
    market_dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    trades, counters = run(frame, market_dates=market_dates)
    assert trades == []
    assert counters["signals_unfilled_missing_next_session"] == 1


def test_zero_volume_next_session_is_unfilled() -> None:
    frame = frame_from_rows(
        [
            ("2024-01-02", 100, 101, 99, 100),
            ("2024-01-03", 100, 101, 99, 100),
            ("2024-01-04", 100, 101, 99, 100),
        ],
        {"2024-01-02"},
    )
    frame.loc["2024-01-03", "Volume"] = 0
    trades, counters = run(frame)
    assert trades == []
    assert counters["signals_unfilled_missing_next_session"] == 1


def test_basic_cost_and_slippage_are_applied_on_both_sides() -> None:
    frame = frame_from_rows(
        [
            ("2024-01-02", 100, 101, 99, 100),
            ("2024-01-03", 100, 140, 99, 130),
        ],
        {"2024-01-02"},
    )
    trades, _ = run(frame, cost_name="basic")
    trade = trades[0]
    expected_entry = 100 * 1.001
    expected_take = expected_entry * 1.30
    expected_exit_fill = expected_take * 0.999
    expected_net = (expected_exit_fill * 0.999) / (expected_entry * 1.001) - 1
    assert trade.entry_fill_price == pytest.approx(expected_entry)
    assert trade.exit_fill_price == pytest.approx(expected_exit_fill)
    assert trade.net_return_pct == pytest.approx(expected_net)


def test_repeat_run_is_deterministic() -> None:
    frame = frame_from_rows(
        [
            ("2024-01-02", 100, 101, 99, 100),
            ("2024-01-03", 100, 131, 99, 130),
        ],
        {"2024-01-02"},
    )
    first, first_counters = run(frame)
    second, second_counters = run(frame)
    assert [trade.to_dict() for trade in first] == [trade.to_dict() for trade in second]
    assert first_counters == second_counters
