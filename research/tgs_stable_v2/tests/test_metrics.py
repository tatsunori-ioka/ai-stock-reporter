from __future__ import annotations

import pandas as pd
import pytest

from tgs_stable_v2.metrics import (
    equal_notional_equity,
    longest_no_signal_period,
    maximum_drawdown,
    portfolio_metrics,
    trade_metrics,
)


def test_trade_statistics() -> None:
    trades = pd.DataFrame(
        [
            {"is_closed": True, "net_return_pct": 0.30, "holding_sessions": 10, "exit_date": "2024-01-10", "ticker": "A"},
            {"is_closed": True, "net_return_pct": -0.10, "holding_sessions": 20, "exit_date": "2024-01-20", "ticker": "B"},
            {"is_closed": True, "net_return_pct": -0.05, "holding_sessions": 30, "exit_date": "2024-01-30", "ticker": "C"},
            {"is_closed": False, "net_return_pct": 0.02, "holding_sessions": 5, "exit_date": "2024-02-01", "ticker": "D"},
        ]
    )
    result = trade_metrics(trades)
    assert result["trade_count"] == 4
    assert result["closed_trade_count"] == 3
    assert result["open_trade_count"] == 1
    assert result["profit_factor"] == pytest.approx(2.0)
    assert result["win_rate"] == pytest.approx(1 / 3)
    assert result["payoff_ratio"] == pytest.approx(4.0)
    assert result["max_consecutive_losses"] == 2
    assert result["average_holding_sessions"] == 20


def test_drawdown_and_portfolio_metrics() -> None:
    dates = pd.date_range("2024-01-01", periods=4)
    curve = pd.DataFrame(
        {
            "date": dates,
            "equity": [1.0, 1.2, 0.9, 1.1],
            "active_positions": [0, 1, 1, 0],
            "capacity": [1, 1, 1, 1],
            "exposure": [0.0, 1.0, 1.0, 0.0],
        }
    )
    assert maximum_drawdown(pd.Series(curve["equity"].values, index=dates)) == pytest.approx(-0.25)
    result = portfolio_metrics(curve)
    assert result["total_return"] == pytest.approx(0.10)
    assert result["maximum_drawdown"] == pytest.approx(-0.25)
    assert result["market_exposure"] == pytest.approx(0.5)
    assert result["maximum_concurrent_positions"] == 1


def test_longest_no_signal_period_uses_market_sessions() -> None:
    market_dates = pd.bdate_range("2024-01-01", periods=10)
    signals = pd.DataFrame({"signal_date": [market_dates[2], market_dates[8]]})
    result = longest_no_signal_period(signals, market_dates)
    assert result["sessions"] == 5
    assert result["start"] == market_dates[3].date().isoformat()
    assert result["end"] == market_dates[7].date().isoformat()
    assert result["calendar_days"] == (market_dates[7] - market_dates[3]).days + 1


def test_longest_no_signal_period_includes_leading_trailing_and_all_empty_runs() -> None:
    market_dates = pd.bdate_range("2024-01-01", periods=10)
    trailing = longest_no_signal_period(
        pd.DataFrame({"signal_date": market_dates[:4]}),
        market_dates,
    )
    assert trailing["sessions"] == 6
    assert trailing["start"] == market_dates[4].date().isoformat()
    assert trailing["end"] == market_dates[-1].date().isoformat()

    no_signals = longest_no_signal_period(
        pd.DataFrame({"signal_date": []}),
        market_dates,
    )
    assert no_signals["sessions"] == 10
    assert no_signals["start"] == market_dates[0].date().isoformat()
    assert no_signals["end"] == market_dates[-1].date().isoformat()

    every_session = longest_no_signal_period(
        pd.DataFrame({"signal_date": market_dates}),
        market_dates,
    )
    assert every_session == {
        "sessions": 0,
        "calendar_days": 0,
        "start": None,
        "end": None,
    }


def test_equal_notional_portfolio_is_deterministic_and_no_leverage() -> None:
    dates = pd.bdate_range("2024-01-02", periods=4)
    frames = {
        "A": pd.DataFrame({"Close": [100, 110, 120, 120]}, index=dates),
        "B": pd.DataFrame({"Close": [100, 100, 90, 100]}, index=dates),
    }
    trades = pd.DataFrame(
        [
            {
                "ticker": "A",
                "entry_date": dates[0].date().isoformat(),
                "exit_date": dates[2].date().isoformat(),
                "entry_fill_price": 100,
                "exit_fill_price": 120,
                "entry_cost_pct": 0,
                "exit_cost_pct": 0,
            },
            {
                "ticker": "B",
                "entry_date": dates[1].date().isoformat(),
                "exit_date": dates[3].date().isoformat(),
                "entry_fill_price": 100,
                "exit_fill_price": 100,
                "entry_cost_pct": 0,
                "exit_cost_pct": 0,
            },
        ]
    )
    first = equal_notional_equity(
        trades,
        frames,
        evaluation_start=dates[0],
        evaluation_end=dates[-1],
    )
    second = equal_notional_equity(
        trades,
        frames,
        evaluation_start=dates[0],
        evaluation_end=dates[-1],
    )
    pd.testing.assert_frame_equal(first, second)
    assert first["capacity"].max() == 2
    assert first["active_positions"].max() == 2
    assert first["exposure"].max() <= 1
    assert first.iloc[-1]["equity"] == pytest.approx(1.10)
