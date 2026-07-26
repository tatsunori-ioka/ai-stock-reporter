from __future__ import annotations

import pandas as pd

from .config import (
    DAILY_RSI_WINDOW,
    SCORE_THRESHOLD,
    SCORE_WEIGHTS,
    VOLUME_MA_WINDOW,
    VOLUME_MULTIPLIER,
    WEEKLY_MA_WINDOW,
)


REQUIRED_OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def normalize_daily(
    frame: pd.DataFrame,
    *,
    drop_nontrading: bool = True,
) -> pd.DataFrame:
    """Return sorted, unique, complete raw OHLCV rows.

    This deliberately mirrors Ver1.0: auto-adjustment is disabled at download
    time and indicators use unadjusted Open/High/Low/Close/Volume.
    """

    missing = [column for column in REQUIRED_OHLCV if column not in frame.columns]
    if missing:
        raise ValueError(f"missing OHLCV columns: {missing}")
    normalized = frame.copy()
    normalized.index = pd.to_datetime(normalized.index).tz_localize(None)
    normalized = normalized[~normalized.index.duplicated(keep="last")].sort_index()
    numeric = [column for column in [*REQUIRED_OHLCV, "Adj Close"] if column in normalized.columns]
    normalized[numeric] = normalized[numeric].apply(pd.to_numeric, errors="coerce")
    normalized = normalized.dropna(subset=REQUIRED_OHLCV)
    nonpositive_ohlc = (normalized[["Open", "High", "Low", "Close"]] <= 0).any(axis=1)
    nonpositive_volume = normalized["Volume"] <= 0
    audit = {
        "nonpositive_ohlc_rows_removed": int(nonpositive_ohlc.sum()),
        "nonpositive_volume_rows_removed": int(nonpositive_volume.sum()),
    }
    if drop_nontrading:
        normalized = normalized.loc[~nonpositive_ohlc & ~nonpositive_volume].copy()
    normalized.attrs.update(audit)
    return normalized


def moving_average(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def rsi(series: pd.Series, window: int = DAILY_RSI_WINDOW) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    relative_strength = avg_gain / avg_loss
    return 100 - (100 / (1 + relative_strength))


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = series.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = series.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return macd_line, signal_line, macd_line - signal_line


def make_weekly_data(daily: pd.DataFrame) -> pd.DataFrame:
    """Build the exact Ver1.0 W-FRI aggregation.

    A Monday-Thursday partial week receives a future Friday label, so it
    cannot flow backward into those daily rows. Friday's close makes that
    week's value available on Friday. A Friday holiday becomes available on
    the following trading session.
    """

    weekly = daily.resample("W-FRI").agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    )
    return weekly.dropna(subset=["Open", "High", "Low", "Close"])


def build_signal_frame(daily: pd.DataFrame) -> pd.DataFrame:
    frame = normalize_daily(daily)
    weekly = make_weekly_data(frame)

    weekly["weekly_200ma"] = moving_average(weekly["Close"], WEEKLY_MA_WINDOW)
    weekly["weekly_macd"], weekly["weekly_macd_signal"], _ = macd(weekly["Close"])
    weekly["weekly_macd_gc"] = (
        (weekly["weekly_macd"] > weekly["weekly_macd_signal"])
        & (weekly["weekly_macd"].shift(1) <= weekly["weekly_macd_signal"].shift(1))
    )
    weekly["weekly_macd_uptrend"] = weekly["weekly_macd"] > weekly["weekly_macd_signal"]
    weekly["weekly_above_200ma"] = weekly["Close"] > weekly["weekly_200ma"]

    weekly_columns = [
        "weekly_200ma",
        "weekly_macd",
        "weekly_macd_signal",
        "weekly_above_200ma",
        "weekly_macd_gc",
        "weekly_macd_uptrend",
    ]
    frame = frame.join(weekly[weekly_columns].reindex(frame.index, method="ffill"))

    frame["daily_rsi"] = rsi(frame["Close"], DAILY_RSI_WINDOW)
    frame["volume_30ma"] = moving_average(frame["Volume"], VOLUME_MA_WINDOW)
    frame["daily_rsi_40_65"] = frame["daily_rsi"].between(40, 65, inclusive="both")
    frame["daily_volume_1_5x"] = frame["Volume"] >= frame["volume_30ma"] * VOLUME_MULTIPLIER

    frame["tgs_score"] = 0
    for column, weight in SCORE_WEIGHTS.items():
        frame["tgs_score"] += frame[column].astype("boolean").fillna(False).astype(int) * weight

    # Ver1.0 turns missing booleans into false. Research results additionally
    # exclude the full indicator warm-up from their measurement period.
    readiness_columns = [
        "weekly_200ma",
        "weekly_macd",
        "weekly_macd_signal",
        "daily_rsi",
        "volume_30ma",
    ]
    frame["indicator_ready"] = frame[readiness_columns].notna().all(axis=1)
    frame["entry_signal"] = frame["indicator_ready"] & (frame["tgs_score"] >= SCORE_THRESHOLD)
    return frame
