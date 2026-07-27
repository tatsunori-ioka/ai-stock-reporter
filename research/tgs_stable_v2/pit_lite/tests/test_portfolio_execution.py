from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
import pandas.testing as pdt
import pytest

from pit_lite.execution import rank_candidates, simulate_capital_proxy
from tgs_stable_v2.config import COST_SCENARIOS


def price_frame(
    sessions: pd.DatetimeIndex,
    *,
    open_: float = 100.0,
    high: float = 105.0,
    low: float = 95.0,
    close: float = 100.0,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": 1_000_000.0,
        },
        index=sessions,
    )


def signals(rows: Iterable[tuple[str, pd.Timestamp, int, float, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=["code", "signal_date", "score", "median_va_60", "sector"],
    )


def simulate(
    event_rows: Iterable[tuple[str, pd.Timestamp, int, float, str]],
    frames: dict[str, pd.DataFrame],
    sessions: pd.DatetimeIndex,
    *,
    maximum_positions: int = 10,
    path_policy: str = "conservative",
    terminal_policy: str = "haircut_20",
):
    return simulate_capital_proxy(
        signals(event_rows),
        frames,
        sessions,
        cost=COST_SCENARIOS["zero"],
        path_policy=path_policy,
        terminal_policy=terminal_policy,
        maximum_positions=maximum_positions,
    )


def test_priority_is_score_then_signal_date_liquidity_then_code() -> None:
    frame = pd.DataFrame(
        [
            {"code": "40000", "score": 90, "median_va_60": 999.0},
            {"code": "30000", "score": 120, "median_va_60": 1.0},
            {"code": "20000", "score": 120, "median_va_60": 2.0},
            {"code": "10000", "score": 120, "median_va_60": 2.0},
        ]
    )
    ranked = rank_candidates(frame)
    assert ranked["code"].tolist() == ["10000", "20000", "30000", "40000"]


def test_capacity_accepts_only_highest_priority_open_candidate() -> None:
    sessions_index = pd.bdate_range("2024-01-02", periods=3)
    frames = {
        code: price_frame(sessions_index)
        for code in ("10000", "20000", "30000")
    }
    event_rows = [
        ("30000", sessions_index[0], 90, 999.0, "A"),
        ("20000", sessions_index[0], 120, 1.0, "A"),
        ("10000", sessions_index[0], 120, 2.0, "A"),
    ]
    ledger, _, counters = simulate(
        event_rows,
        frames,
        sessions_index,
        maximum_positions=1,
    )
    assert counters["accepted_entries"] == 1
    assert counters["capacity_rejections"] == 2
    assert ledger["code"].tolist() == ["10000"]


def test_duplicate_signal_does_not_open_second_same_ticker_position() -> None:
    sessions_index = pd.bdate_range("2024-01-02", periods=4)
    frames = {"10000": price_frame(sessions_index)}
    ledger, _, counters = simulate(
        [
            ("10000", sessions_index[0], 90, 1.0, "A"),
            ("10000", sessions_index[1], 120, 2.0, "A"),
        ],
        frames,
        sessions_index,
    )
    assert counters["accepted_entries"] == 1
    assert counters["duplicate_rejections"] == 1
    assert len(ledger) == 1


def test_missing_or_invalid_immediate_next_session_is_never_filled_later() -> None:
    sessions_index = pd.bdate_range("2024-01-02", periods=4)
    missing_frame = price_frame(sessions_index.delete(1))
    invalid_frame = price_frame(sessions_index)
    invalid_frame.loc[sessions_index[1], "Volume"] = 0
    _, _, missing = simulate(
        [("10000", sessions_index[0], 90, 1.0, "A")],
        {"10000": missing_frame},
        sessions_index,
    )
    _, _, invalid = simulate(
        [("20000", sessions_index[0], 90, 1.0, "A")],
        {"20000": invalid_frame},
        sessions_index,
    )
    assert missing["missing_next_session_rejections"] == 1
    assert missing["accepted_entries"] == 0
    assert invalid["invalid_bar_rejections"] == 1
    assert invalid["accepted_entries"] == 0


def test_gap_exit_at_open_releases_capacity_for_same_open_entry() -> None:
    sessions_index = pd.bdate_range("2024-01-02", periods=4)
    first = price_frame(sessions_index)
    first.loc[sessions_index[2], ["Open", "High", "Low", "Close"]] = [
        80.0,
        85.0,
        75.0,
        82.0,
    ]
    second = price_frame(sessions_index)
    ledger, _, counters = simulate(
        [
            ("10000", sessions_index[0], 90, 1.0, "A"),
            ("20000", sessions_index[1], 90, 1.0, "B"),
        ],
        {"10000": first, "20000": second},
        sessions_index,
        maximum_positions=1,
    )
    first_trade = ledger.loc[ledger["code"] == "10000"].iloc[0]
    assert first_trade["exit_reason"] == "stop_gap"
    assert first_trade["exit_raw_price"] == 80.0
    assert counters["accepted_entries"] == 2
    assert counters["capacity_rejections"] == 0
    assert set(ledger["code"]) == {"10000", "20000"}


def test_intraday_exit_cannot_retroactively_fund_same_open_entry() -> None:
    sessions_index = pd.bdate_range("2024-01-02", periods=4)
    first = price_frame(sessions_index)
    first.loc[sessions_index[2], ["Open", "High", "Low", "Close"]] = [
        100.0,
        135.0,
        95.0,
        130.0,
    ]
    second = price_frame(sessions_index)
    ledger, _, counters = simulate(
        [
            ("10000", sessions_index[0], 90, 1.0, "A"),
            ("20000", sessions_index[1], 120, 2.0, "B"),
        ],
        {"10000": first, "20000": second},
        sessions_index,
        maximum_positions=1,
    )
    assert counters["accepted_entries"] == 1
    assert counters["capacity_rejections"] == 1
    assert ledger.iloc[0]["code"] == "10000"
    assert ledger.iloc[0]["exit_reason"] == "take_profit"


def test_entry_day_stop_take_is_enabled_and_path_policy_is_explicit() -> None:
    sessions_index = pd.bdate_range("2024-01-02", periods=2)
    frame = price_frame(sessions_index)
    frame.loc[sessions_index[1], ["Open", "High", "Low", "Close"]] = [
        100.0,
        135.0,
        85.0,
        100.0,
    ]
    conservative, _, _ = simulate(
        [("10000", sessions_index[0], 90, 1.0, "A")],
        {"10000": frame},
        sessions_index,
        path_policy="conservative",
    )
    optimistic, _, _ = simulate(
        [("10000", sessions_index[0], 90, 1.0, "A")],
        {"10000": frame},
        sessions_index,
        path_policy="optimistic",
    )
    assert conservative.iloc[0]["holding_sessions"] == 1
    assert conservative.iloc[0]["exit_reason"].endswith("stop_first")
    assert conservative.iloc[0]["exit_raw_price"] == pytest.approx(90.0)
    assert optimistic.iloc[0]["exit_reason"].endswith("take_first")
    assert optimistic.iloc[0]["exit_raw_price"] == pytest.approx(130.0)


@pytest.mark.parametrize(
    ("open_price", "expected_reason"),
    [(85.0, "stop_gap"), (135.0, "take_profit_gap")],
)
def test_overnight_gap_fills_at_open(
    open_price: float,
    expected_reason: str,
) -> None:
    sessions_index = pd.bdate_range("2024-01-02", periods=3)
    frame = price_frame(sessions_index)
    frame.loc[sessions_index[2], ["Open", "High", "Low", "Close"]] = [
        open_price,
        max(open_price, 100.0),
        min(open_price, 100.0),
        open_price,
    ]
    ledger, _, _ = simulate(
        [("10000", sessions_index[0], 90, 1.0, "A")],
        {"10000": frame},
        sessions_index,
    )
    assert ledger.iloc[0]["exit_reason"] == expected_reason
    assert ledger.iloc[0]["exit_raw_price"] == open_price


def test_max_holding_exits_on_60th_valid_ticker_session() -> None:
    sessions_index = pd.bdate_range("2024-01-02", periods=61)
    frame = price_frame(sessions_index, close=101.0)
    ledger, _, _ = simulate(
        [("10000", sessions_index[0], 90, 1.0, "A")],
        {"10000": frame},
        sessions_index,
    )
    assert ledger.iloc[0]["entry_date"] == sessions_index[1].date().isoformat()
    assert ledger.iloc[0]["exit_date"] == sessions_index[60].date().isoformat()
    assert ledger.iloc[0]["holding_sessions"] == 60
    assert ledger.iloc[0]["exit_reason"] == "max_holding"
    assert ledger.iloc[0]["exit_raw_price"] == 101.0


def test_missing_bar_while_open_is_not_a_holding_session() -> None:
    sessions_index = pd.bdate_range("2024-01-02", periods=62)
    frame = price_frame(sessions_index.delete(2), close=101.0)
    ledger, _, _ = simulate(
        [("10000", sessions_index[0], 90, 1.0, "A")],
        {"10000": frame},
        sessions_index,
    )
    assert ledger.iloc[0]["holding_sessions"] == 60
    assert ledger.iloc[0]["exit_date"] == sessions_index[61].date().isoformat()
    assert ledger.iloc[0]["exit_reason"] == "max_holding"


def test_position_size_is_at_most_ten_percent_of_open_equity_and_no_leverage() -> None:
    sessions_index = pd.bdate_range("2024-01-02", periods=3)
    codes = [f"{number:05d}" for number in range(10000, 10011)]
    frames = {code: price_frame(sessions_index) for code in codes}
    event_rows = [
        (code, sessions_index[0], 90, float(100 - index), "A")
        for index, code in enumerate(codes)
    ]
    ledger, curve, counters = simulate(event_rows, frames, sessions_index)
    accepted = ledger.loc[ledger["entry_date"] == sessions_index[1].date().isoformat()]
    assert counters["accepted_entries"] == 10
    assert counters["capacity_rejections"] == 1
    assert len(accepted) == 10
    assert all(
        accepted["shares"] * accepted["entry_fill_price"] <= 1_000_000.0 + 1e-6
    )
    assert curve["cash"].min() >= 0.0
    assert curve["active_positions"].max() <= 10


@pytest.mark.parametrize(
    ("terminal_policy", "expected_reason", "expected_price"),
    [
        ("haircut_20", "premature_data_end_haircut", 80.0),
        ("last_close", "premature_data_end_last_close", 100.0),
    ],
)
def test_premature_data_end_terminal_semantics(
    terminal_policy: str,
    expected_reason: str,
    expected_price: float,
) -> None:
    sessions_index = pd.bdate_range("2024-01-02", periods=4)
    frame = price_frame(sessions_index[:-1])
    ledger, curve, counters = simulate(
        [("10000", sessions_index[0], 90, 1.0, "A")],
        {"10000": frame},
        sessions_index,
        terminal_policy=terminal_policy,
    )
    assert counters["premature_data_end_suspicions"] == 1
    assert ledger.iloc[0]["exit_reason"] == expected_reason
    assert ledger.iloc[0]["exit_raw_price"] == expected_price
    assert ledger.iloc[0]["data_quality_status"] == "premature_data_end_suspicion"
    assert ledger.iloc[0]["exit_date"] == sessions_index[-1].date().isoformat()
    assert ledger.iloc[0]["last_observed_bar_date"] == sessions_index[-2].date().isoformat()
    assert bool(ledger.iloc[0]["is_closed"]) is True
    assert curve.iloc[-1]["active_positions"] == 0


def test_normal_frozen_end_position_is_right_censored_without_haircut() -> None:
    sessions_index = pd.bdate_range("2024-01-02", periods=4)
    frame = price_frame(sessions_index, close=102.0)
    ledger, _, counters = simulate(
        [("10000", sessions_index[0], 90, 1.0, "A")],
        {"10000": frame},
        sessions_index,
    )
    assert counters["premature_data_end_suspicions"] == 0
    assert ledger.iloc[0]["exit_reason"] == "open_at_frozen_end"
    assert ledger.iloc[0]["exit_raw_price"] == 102.0
    assert bool(ledger.iloc[0]["is_closed"]) is False
    assert ledger.iloc[0]["data_quality_status"] == "right_censored_mark_to_market"


def test_same_synthetic_inputs_are_bitwise_deterministic() -> None:
    sessions_index = pd.bdate_range("2024-01-02", periods=5)
    frames = {
        "10000": price_frame(sessions_index),
        "20000": price_frame(sessions_index),
    }
    event_rows = [
        ("20000", sessions_index[0], 90, 1.0, "A"),
        ("10000", sessions_index[0], 90, 1.0, "A"),
    ]
    first = simulate(event_rows, frames, sessions_index)
    second = simulate(event_rows, frames, sessions_index)
    pdt.assert_frame_equal(first[0], second[0], check_exact=True)
    pdt.assert_frame_equal(first[1], second[1], check_exact=True)
    assert first[2] == second[2]
