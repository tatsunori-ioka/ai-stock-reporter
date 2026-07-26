from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from .indicators import REQUIRED_OHLCV, normalize_daily


def _safe_name(ticker: str) -> str:
    return ticker.replace(".", "_").replace("/", "_")


def frame_sha256(frame: pd.DataFrame) -> str:
    canonical = frame.to_csv(index=True, date_format="%Y-%m-%d", float_format="%.10g")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _extract_ticker(downloaded: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if downloaded.empty:
        return pd.DataFrame()
    if isinstance(downloaded.columns, pd.MultiIndex):
        level_zero = downloaded.columns.get_level_values(0)
        level_one = downloaded.columns.get_level_values(1)
        if ticker in level_zero:
            frame = downloaded[ticker].copy()
        elif ticker in level_one:
            frame = downloaded.xs(ticker, axis=1, level=1).copy()
        else:
            return pd.DataFrame()
    else:
        frame = downloaded.copy()
    return normalize_daily(frame, drop_nontrading=False)


def download_daily_data(
    tickers: list[str],
    *,
    start: str,
    end: str,
    cache_dir: Path,
    refresh: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Download raw yfinance OHLCV or load an exact local research cache."""

    cache_dir.mkdir(parents=True, exist_ok=True)
    request = {
        "tickers": tickers,
        "start": start,
        "end_exclusive": end,
        "auto_adjust": False,
        "group_by": "ticker",
        "interval": "1d",
    }
    request_path = cache_dir / "request.json"
    expected_files = {ticker: cache_dir / f"{_safe_name(ticker)}.csv" for ticker in tickers}

    can_reuse = (
        not refresh
        and request_path.exists()
        and all(path.exists() for path in expected_files.values())
        and json.loads(request_path.read_text(encoding="utf-8")) == request
    )
    frames: dict[str, pd.DataFrame] = {}
    if can_reuse:
        for ticker, path in expected_files.items():
            cached = pd.read_csv(path, index_col="Date", parse_dates=["Date"])
            frames[ticker] = normalize_daily(cached)
        provider_version = json.loads((cache_dir / "provider.json").read_text(encoding="utf-8"))
        return frames, {"request": request, "cache_reused": True, **provider_version}

    import yfinance as yf

    downloaded = yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=False,
        group_by="ticker",
        interval="1d",
        threads=True,
        progress=False,
    )
    for ticker, path in expected_files.items():
        raw_frame = _extract_ticker(downloaded, ticker)
        if raw_frame.empty:
            raise RuntimeError(f"no complete OHLCV rows returned for {ticker}")
        raw_frame.to_csv(path, index_label="Date", date_format="%Y-%m-%d")
        frames[ticker] = normalize_daily(raw_frame)

    provider = {
        "provider": "Yahoo Finance via yfinance",
        "yfinance_version": getattr(yf, "__version__", "unknown"),
        "pandas_version": pd.__version__,
        "retrieved_on": date.today().isoformat(),
    }
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (cache_dir / "provider.json").write_text(
        json.dumps(provider, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return frames, {"request": request, "cache_reused": False, **provider}


def availability_rows(frames: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    all_dates: set[pd.Timestamp] = set()
    for frame in frames.values():
        all_dates.update(pd.Timestamp(value) for value in frame.index)

    rows: list[dict[str, Any]] = []
    for ticker, frame in frames.items():
        index_set = {pd.Timestamp(value) for value in frame.index}
        relevant_union = {
            value
            for value in all_dates
            if frame.index.min() <= value <= frame.index.max()
        }
        adjusted_ratio_changes = 0
        adjusted_ratio_min: float | None = None
        adjusted_ratio_max: float | None = None
        if "Adj Close" in frame.columns:
            ratio = (frame["Adj Close"] / frame["Close"]).replace([float("inf"), -float("inf")], pd.NA).dropna()
            if not ratio.empty:
                adjusted_ratio_min = float(ratio.min())
                adjusted_ratio_max = float(ratio.max())
                # Yahoo values carry small per-row floating noise. Count only
                # economically material step changes (for example dividend or
                # split adjustment-factor changes), not binary rounding noise.
                adjusted_ratio_changes = int((ratio.pct_change().abs() > 0.0001).sum())
        rows.append(
            {
                "ticker": ticker,
                "first_date": frame.index.min().date().isoformat(),
                "last_date": frame.index.max().date().isoformat(),
                "rows": int(len(frame)),
                "duplicate_dates": int(frame.index.duplicated().sum()),
                "missing_vs_union_sessions": int(len(relevant_union - index_set)),
                "nonpositive_ohlc_rows_removed": int(
                    frame.attrs.get("nonpositive_ohlc_rows_removed", 0)
                ),
                "nonpositive_volume_rows_removed": int(
                    frame.attrs.get("nonpositive_volume_rows_removed", 0)
                ),
                "adj_close_available": "Adj Close" in frame.columns,
                "adj_close_ratio_min": adjusted_ratio_min,
                "adj_close_ratio_max": adjusted_ratio_max,
                "adj_close_ratio_material_change_count": max(0, adjusted_ratio_changes),
                "raw_sha256": frame_sha256(frame),
            }
        )
    return rows


def maximum_common_window(frames: dict[str, pd.DataFrame]) -> tuple[pd.Timestamp, pd.Timestamp]:
    return (
        max(frame.index.min() for frame in frames.values()),
        min(frame.index.max() for frame in frames.values()),
    )
