from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

import stable_cloud_score_check as production
from tgs_stable_v2.indicators import build_signal_frame, make_weekly_data, normalize_daily


def synthetic_daily(periods: int = 1800, start: str = "2010-01-04") -> pd.DataFrame:
    index = pd.bdate_range(start, periods=periods)
    phase = np.arange(periods)
    close = 100 + phase * 0.03 + np.sin(phase / 11.0) * 4
    volume = 1_000_000 + (phase % 37) * 30_000
    volume[::43] *= 3
    return pd.DataFrame(
        {
            "Open": close * 0.998,
            "High": close * 1.015,
            "Low": close * 0.985,
            "Close": close,
            "Adj Close": close * 0.97,
            "Volume": volume,
        },
        index=index,
    )


def test_indicator_and_score_parity_with_production() -> None:
    daily = synthetic_daily()
    research = build_signal_frame(daily)
    expected = production.build_signal_frame(daily[["Open", "High", "Low", "Close", "Volume"]])
    columns = [
        "weekly_200ma",
        "weekly_macd",
        "weekly_macd_signal",
        "weekly_above_200ma",
        "weekly_macd_gc",
        "weekly_macd_uptrend",
        "daily_rsi",
        "volume_30ma",
        "daily_rsi_40_65",
        "daily_volume_1_5x",
        "tgs_score",
    ]
    assert_frame_equal(research[columns], expected[columns], check_dtype=False)


def test_weekly_aggregation_matches_frozen_contract() -> None:
    daily = synthetic_daily(periods=10)
    weekly = make_weekly_data(daily)
    first_week = daily.loc[:"2010-01-08"]
    assert weekly.iloc[0]["Open"] == first_week.iloc[0]["Open"]
    assert weekly.iloc[0]["High"] == first_week["High"].max()
    assert weekly.iloc[0]["Low"] == first_week["Low"].min()
    assert weekly.iloc[0]["Close"] == first_week.iloc[-1]["Close"]
    assert weekly.iloc[0]["Volume"] == first_week["Volume"].sum()


def test_partial_week_cannot_flow_backward() -> None:
    full = synthetic_daily(periods=1800)
    cutoff = full.index[-3]  # A mid-week cutoff for this deterministic range.
    while cutoff.weekday() >= 4:
        cutoff -= pd.Timedelta(days=1)
    truncated = full.loc[:cutoff]
    full_result = build_signal_frame(full)
    truncated_result = build_signal_frame(truncated)
    columns = ["weekly_200ma", "weekly_macd", "weekly_macd_signal", "tgs_score"]
    assert_frame_equal(
        full_result.loc[truncated.index, columns],
        truncated_result[columns],
        check_dtype=False,
    )


def test_full_history_is_prefix_stable_no_lookahead() -> None:
    daily = synthetic_daily(periods=1700)
    cutoff = daily.index[1500]
    full = build_signal_frame(daily)
    truncated = build_signal_frame(daily.loc[:cutoff])
    assert_series_equal(
        full.loc[:cutoff, "tgs_score"],
        truncated["tgs_score"],
        check_names=False,
    )


def test_full_history_matches_production_eight_year_seed_after_warmup() -> None:
    daily = synthetic_daily(periods=4200, start="2005-01-03")
    cutoff = daily.index[-1]
    production_window_start = cutoff - pd.Timedelta(days=365 * 8)
    full = build_signal_frame(daily)
    rolling_seed = build_signal_frame(daily.loc[daily.index >= production_window_start])
    columns = [
        "weekly_above_200ma",
        "weekly_macd_gc",
        "weekly_macd_uptrend",
        "daily_rsi_40_65",
        "daily_volume_1_5x",
        "tgs_score",
    ]
    assert full.loc[cutoff, columns].to_dict() == rolling_seed.loc[cutoff, columns].to_dict()
    assert full.loc[cutoff, "weekly_200ma"] == pytest.approx(
        rolling_seed.loc[cutoff, "weekly_200ma"]
    )


def test_warmup_is_explicitly_excluded() -> None:
    frame = build_signal_frame(synthetic_daily(periods=1200))
    first_ready = frame.index[frame["indicator_ready"]][0]
    assert not frame.loc[frame.index < first_ready, "entry_signal"].any()
    assert frame.loc[first_ready, "weekly_200ma"] == frame.loc[first_ready, "weekly_200ma"]


def test_volume_average_includes_current_session() -> None:
    daily = synthetic_daily(periods=40)
    result = build_signal_frame(daily)
    expected = daily["Volume"].iloc[-30:].mean()
    assert result.iloc[-1]["volume_30ma"] == expected


def test_zero_volume_provider_placeholder_is_not_a_trading_session() -> None:
    daily = synthetic_daily(periods=40)
    placeholder_date = daily.index[10]
    daily.loc[placeholder_date, "Volume"] = 0
    normalized = normalize_daily(daily)
    assert placeholder_date not in normalized.index
    assert normalized.attrs["nonpositive_volume_rows_removed"] == 1
