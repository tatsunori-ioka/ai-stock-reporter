#!/usr/bin/env python3
"""TGS Stable Ver1.0 cloud daily score check.

Phase 1 scope:
- Calculate the frozen Stable Ver1.0 score for the 15 Stable tickers.
- Write score rows to the official Google Sheets paper ledger when --execute is set.
- Update Dashboard summary tabs when a dashboard spreadsheet id is configured.
- Never create pending orders, never update positions, and never send real orders.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf


JST = ZoneInfo("Asia/Tokyo")
RULE_VERSION = "stable-1.0"
STRATEGY_NAME = "TGS Stable Ver1.0"
MARKET_NAME = "JP Stocks"

SCORE_THRESHOLD = 90
STOP_LOSS_PCT = -0.10
TAKE_PROFIT_PCT = 0.30
MAX_HOLDING_DAYS = 60

WEEKLY_MA_WINDOW = 200
DAILY_RSI_WINDOW = 14
VOLUME_MA_WINDOW = 30
VOLUME_MULTIPLIER = 1.5

STABLE_TICKERS = [
    "6273.T",
    "6301.T",
    "6367.T",
    "7011.T",
    "5801.T",
    "5802.T",
    "5803.T",
    "8801.T",
    "8802.T",
    "8001.T",
    "8002.T",
    "8015.T",
    "8031.T",
    "8053.T",
    "8058.T",
]

SCORE_WEIGHTS = {
    "weekly_above_200ma": 30,
    "weekly_macd_gc": 30,
    "weekly_macd_uptrend": 20,
    "daily_rsi_40_65": 20,
    "daily_volume_1_5x": 20,
}

REPORT_COLUMNS = [
    "date",
    "ticker",
    "name",
    "weekly_above_200ma",
    "weekly_macd_gc",
    "weekly_macd_uptrend",
    "daily_rsi_40_65",
    "daily_volume_1_5x",
    "stable_score",
    "signal_expected",
    "close",
    "daily_rsi",
    "volume_ratio",
    "data_latest_date",
    "data_status",
    "rule_version",
    "updated_at",
]

PENDING_COLUMNS = [
    "pending_order_id",
    "signal_date",
    "ticker",
    "name",
    "sector",
    "tgs_score",
    "daily_rsi",
    "volume_ratio",
    "planned_entry",
    "status",
]

POSITION_COLUMNS = [
    "paper_trade_id",
    "ticker",
    "name",
    "sector",
    "signal_date",
    "entry_date",
    "entry_price",
    "shares",
    "allocation",
    "stop_price",
    "take_profit_price",
    "max_holding_days",
    "status",
]

TRADE_COLUMNS = [
    "timestamp",
    "paper_trade_id",
    "side",
    "ticker",
    "name",
    "sector",
    "price",
    "shares",
    "cash_amount",
    "reason",
    "pnl",
    "return_pct",
    "signal_date",
    "entry_date",
    "exit_date",
    "rule_version",
]

ACCOUNT_COLUMNS = [
    "as_of",
    "cash",
    "initial_capital",
    "realized_pnl",
    "open_positions",
    "pending_orders",
    "market_value",
    "equity",
]

DAILY_LOG_COLUMNS = [
    "report_date",
    "row_type",
    "ticker",
    "name",
    "sector",
    "action",
    "reason",
    "status",
    "signal_date",
    "entry_date",
    "entry_price",
    "open",
    "high",
    "low",
    "close",
    "stop_price",
    "take_profit_price",
    "holding_days",
    "shares",
    "market_value",
    "unrealized_return_pct",
    "realized_pnl",
    "paper_trade_id",
    "pending_order_id",
    "notes",
]

RUN_LOG_COLUMNS = [
    "timestamp",
    "run_id",
    "script",
    "mode",
    "status",
    "as_of",
    "rows_scored",
    "signal_count",
    "max_score_ticker",
    "max_score",
    "ledger_spreadsheet_id",
    "dashboard_spreadsheet_id",
    "error_message",
]

TGS_COLUMNS = [
    "date",
    "strategy",
    "market",
    "signal_count",
    "trade_count",
    "win_count",
    "loss_count",
    "win_rate",
    "pnl",
    "profit_factor",
    "max_drawdown",
    "status",
    "source_file",
    "note",
    "updated_at",
]

HOME_COLUMNS = ["section", "metric", "value", "status", "updated_at", "note"]

LOG_COLUMNS = [
    "timestamp",
    "run_id",
    "script",
    "action",
    "status",
    "rows_read",
    "rows_written",
    "target_sheet",
    "source_file",
    "error_message",
    "project",
    "event_type",
    "summary",
    "result",
    "next_action",
]

LEDGER_TABS = {
    "TGS_Pending": PENDING_COLUMNS,
    "TGS_Positions": POSITION_COLUMNS,
    "TGS_Trade_History": TRADE_COLUMNS,
    "TGS_Account": ACCOUNT_COLUMNS,
    "TGS_Daily_Log": DAILY_LOG_COLUMNS,
    "TGS_Daily_Score_Check": REPORT_COLUMNS,
    "TGS_Run_Log": RUN_LOG_COLUMNS,
}


@dataclass(frozen=True)
class ScoreSummary:
    as_of: str
    rows_scored: int
    signal_count: int
    max_score_ticker: str
    max_score: float
    status: str
    source_file: str
    note: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="", help="Score date in YYYY-MM-DD. Default: today in JST.")
    parser.add_argument("--execute", action="store_true", help="Write to Google Sheets. Default is dry-run only.")
    parser.add_argument("--init-only", action="store_true", help="Only create/verify ledger tabs and headers.")
    parser.add_argument("--out-dir", type=Path, default=Path("outputs/cloud_score_check"))
    parser.add_argument("--metadata", type=Path, default=Path("stable_universe_metadata.csv"))
    parser.add_argument("--ledger-spreadsheet-id", default=os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", ""))
    parser.add_argument(
        "--dashboard-spreadsheet-id",
        default=(
            os.getenv("GOOGLE_DASHBOARD_SPREADSHEET_ID")
            or os.getenv("TGS_DASHBOARD_SPREADSHEET_ID")
            or os.getenv("GOOGLE_SPREADSHEET_ID")
            or ""
        ),
    )
    parser.add_argument("--skip-dashboard", action="store_true", help="Do not update Dashboard tabs.")
    parser.add_argument("--verify-only", action="store_true", help="Read Google Sheets state without writing.")
    return parser.parse_args()


def parse_as_of(value: str) -> date:
    if value:
        return date.fromisoformat(value[:10])
    return datetime.now(JST).date()


def now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")


def run_id(updated_at: str) -> str:
    return f"tgs-stable-cloud-score-check-{updated_at.replace('-', '').replace(':', '').replace(' ', 'T')}"


def load_metadata(path: Path) -> dict[str, dict[str, str]]:
    candidates = [path, Path("stable_universe_metadata.csv")]
    source = next((candidate for candidate in candidates if candidate.exists()), None)
    if source is None:
        return {ticker: {"ticker": ticker, "name": "", "sector": ""} for ticker in STABLE_TICKERS}
    with source.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        ticker = str(row.get("ticker", "")).strip()
        if ticker:
            result[ticker] = row
    return result


def moving_average(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def rsi(series: pd.Series, window: int = DAILY_RSI_WINDOW) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = series.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = series.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def make_weekly_data(daily: pd.DataFrame) -> pd.DataFrame:
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
    frame = daily.copy()
    weekly = make_weekly_data(daily)

    weekly["weekly_200ma"] = moving_average(weekly["Close"], WEEKLY_MA_WINDOW)
    weekly["weekly_macd"], weekly["weekly_macd_signal"], _ = macd(weekly["Close"])
    weekly["weekly_macd_gc"] = (
        (weekly["weekly_macd"] > weekly["weekly_macd_signal"])
        & (weekly["weekly_macd"].shift(1) <= weekly["weekly_macd_signal"].shift(1))
    )
    weekly["weekly_macd_uptrend"] = weekly["weekly_macd"] > weekly["weekly_macd_signal"]
    weekly["weekly_above_200ma"] = weekly["Close"] > weekly["weekly_200ma"]

    weekly_signals = weekly[
        [
            "weekly_200ma",
            "weekly_macd",
            "weekly_macd_signal",
            "weekly_above_200ma",
            "weekly_macd_gc",
            "weekly_macd_uptrend",
        ]
    ]
    frame = frame.join(weekly_signals.reindex(frame.index, method="ffill"))

    frame["daily_rsi"] = rsi(frame["Close"], DAILY_RSI_WINDOW)
    frame["volume_30ma"] = moving_average(frame["Volume"], VOLUME_MA_WINDOW)
    frame["daily_rsi_40_65"] = frame["daily_rsi"].between(40, 65, inclusive="both")
    frame["daily_volume_1_5x"] = frame["Volume"] >= frame["volume_30ma"] * VOLUME_MULTIPLIER

    frame["tgs_score"] = 0
    for column, weight in SCORE_WEIGHTS.items():
        frame["tgs_score"] += frame[column].astype("boolean").fillna(False).astype(int) * weight
    frame["entry_signal"] = frame["tgs_score"] >= SCORE_THRESHOLD
    return frame


def normalize_downloaded_data(downloaded: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if downloaded.empty:
        return pd.DataFrame()
    if isinstance(downloaded.columns, pd.MultiIndex):
        if ticker not in downloaded.columns.get_level_values(0):
            return pd.DataFrame()
        daily = downloaded[ticker].copy()
    else:
        daily = downloaded.copy()

    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in daily.columns]
    if missing:
        return pd.DataFrame()
    daily = daily[required].dropna(subset=required)
    daily.index = pd.to_datetime(daily.index).tz_localize(None)
    return daily.sort_index()


def bool_text(value: Any) -> str:
    if pd.isna(value):
        return "false"
    return "true" if bool(value) else "false"


def float_text(value: Any, digits: int = 6) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}"


def build_score_rows(as_of: date, metadata_path: Path, updated_at: str) -> list[dict[str, Any]]:
    metadata = load_metadata(metadata_path)
    start = (as_of - timedelta(days=365 * 8)).isoformat()
    end = (as_of + timedelta(days=1)).isoformat()
    downloaded = yf.download(
        STABLE_TICKERS,
        start=start,
        end=end,
        auto_adjust=False,
        group_by="ticker",
        threads=True,
        progress=False,
    )

    rows: list[dict[str, Any]] = []
    for ticker in STABLE_TICKERS:
        daily = normalize_downloaded_data(downloaded, ticker)
        meta = metadata.get(ticker, {})
        if daily.empty:
            rows.append(empty_score_row(as_of, ticker, meta, updated_at, "no_price_data"))
            continue

        frame = build_signal_frame(daily)
        frame = frame[frame.index.date <= as_of]
        if frame.empty:
            rows.append(empty_score_row(as_of, ticker, meta, updated_at, "no_bar_on_or_before_as_of"))
            continue

        signal = frame.iloc[-1]
        signal_date = frame.index[-1].date().isoformat()
        score = int(signal["tgs_score"])
        volume_ma = signal.get("volume_30ma")
        volume_ratio = "" if pd.isna(volume_ma) or float(volume_ma) == 0 else float(signal["Volume"]) / float(volume_ma)
        rows.append(
            {
                "date": signal_date,
                "ticker": ticker,
                "name": meta.get("name", ""),
                "weekly_above_200ma": bool_text(signal["weekly_above_200ma"]),
                "weekly_macd_gc": bool_text(signal["weekly_macd_gc"]),
                "weekly_macd_uptrend": bool_text(signal["weekly_macd_uptrend"]),
                "daily_rsi_40_65": bool_text(signal["daily_rsi_40_65"]),
                "daily_volume_1_5x": bool_text(signal["daily_volume_1_5x"]),
                "stable_score": score,
                "signal_expected": "true" if score >= SCORE_THRESHOLD else "false",
                "close": float_text(signal["Close"]),
                "daily_rsi": float_text(signal["daily_rsi"]),
                "volume_ratio": "" if volume_ratio == "" else f"{volume_ratio:.6f}",
                "data_latest_date": signal_date,
                "data_status": "ok",
                "rule_version": RULE_VERSION,
                "updated_at": updated_at,
            }
        )
    return rows


def empty_score_row(as_of: date, ticker: str, meta: dict[str, str], updated_at: str, status: str) -> dict[str, Any]:
    return {
        "date": as_of.isoformat(),
        "ticker": ticker,
        "name": meta.get("name", ""),
        "weekly_above_200ma": "false",
        "weekly_macd_gc": "false",
        "weekly_macd_uptrend": "false",
        "daily_rsi_40_65": "false",
        "daily_volume_1_5x": "false",
        "stable_score": "",
        "signal_expected": "false",
        "close": "",
        "daily_rsi": "",
        "volume_ratio": "",
        "data_latest_date": "",
        "data_status": status,
        "rule_version": RULE_VERSION,
        "updated_at": updated_at,
    }


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def score_summary(rows: list[dict[str, Any]], source_file: str) -> ScoreSummary:
    scored = [row for row in rows if row.get("data_status") == "ok"]
    score_pairs = [(row, safe_float(row.get("stable_score")) or 0.0) for row in scored]
    signal_count = sum(1 for _, score in score_pairs if score >= SCORE_THRESHOLD)
    max_row, max_score = max(score_pairs, key=lambda item: item[1], default=({}, 0.0))
    max_ticker = str(max_row.get("ticker", ""))
    status = "signal_detected" if signal_count else "no_signal"
    report_date = str(rows[0].get("date", "")) if rows else ""
    note = f"max_score_ticker={max_ticker} max_score={format_number(max_score)}"
    return ScoreSummary(
        as_of=report_date,
        rows_scored=len(scored),
        signal_count=signal_count,
        max_score_ticker=max_ticker,
        max_score=max_score,
        status=status,
        source_file=source_file,
        note=note,
    )


def safe_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def format_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def build_sheets_service():
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("google-auth and google-api-python-client are required.") from exc

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    ]
    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw_json:
        credentials = service_account.Credentials.from_service_account_info(json.loads(raw_json), scopes=scopes)
    else:
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        if not credentials_path:
            raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_APPLICATION_CREDENTIALS.")
        credentials = service_account.Credentials.from_service_account_file(credentials_path, scopes=scopes)
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def quote_sheet(name: str) -> str:
    return f"'{name.replace(chr(39), chr(39) + chr(39))}'"


def column_letter(index: int) -> str:
    letters = ""
    current = index
    while current:
        current, remainder = divmod(current - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def read_values(service: Any, spreadsheet_id: str, sheet: str, start_row: int, width: int) -> list[list[Any]]:
    end_col = column_letter(width)
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{quote_sheet(sheet)}!A{start_row}:{end_col}")
        .execute()
    )
    return result.get("values", [])


def read_values_optional(service: Any, spreadsheet_id: str, sheet: str, start_row: int, width: int) -> list[list[Any]]:
    try:
        return read_values(service, spreadsheet_id, sheet, start_row, width)
    except Exception:
        return []


def write_values(service: Any, spreadsheet_id: str, range_name: str, values: list[list[Any]]) -> None:
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="RAW",
        body={"values": values},
    ).execute()


def ensure_sheet_exists(service: Any, spreadsheet_id: str, title: str) -> None:
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="sheets.properties.title").execute()
    titles = {item["properties"]["title"] for item in spreadsheet.get("sheets", [])}
    if title in titles:
        return
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
    ).execute()


def trim_trailing_empty(values: list[str]) -> list[str]:
    index = len(values)
    while index > 0 and values[index - 1] == "":
        index -= 1
    return values[:index]


def ensure_header(service: Any, spreadsheet_id: str, sheet: str, columns: list[str], preserve_existing: bool = True) -> list[str]:
    ensure_sheet_exists(service, spreadsheet_id, sheet)
    values = read_values(service, spreadsheet_id, sheet, 1, max(len(columns), 30))
    existing = trim_trailing_empty([str(value) for value in values[0]]) if values else []
    if not existing:
        header = columns
    elif preserve_existing:
        header = existing + [column for column in columns if column not in existing]
    else:
        header = columns
    if header != existing:
        write_values(service, spreadsheet_id, f"{quote_sheet(sheet)}!A1:{column_letter(len(header))}1", [header])
    return header


def row_to_values(row: dict[str, Any], columns: list[str]) -> list[Any]:
    return [row.get(column, "") for column in columns]


def values_to_rows(values: list[list[Any]], columns: list[str]) -> list[dict[str, Any]]:
    return [
        {column: values_row[index] if index < len(values_row) else "" for index, column in enumerate(columns)}
        for values_row in values
    ]


def row_key(row: dict[str, Any], columns: list[str]) -> str:
    return "|".join(str(row.get(column, "")) for column in columns)


def upsert_rows(
    service: Any,
    spreadsheet_id: str,
    sheet: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    key_columns: list[str],
) -> dict[str, int]:
    existing_values = read_values(service, spreadsheet_id, sheet, 1, max(len(columns), 30))
    existing_rows = values_to_rows(existing_values[1:], columns) if len(existing_values) > 1 else []
    existing_keys = {row_key(row, key_columns): index for index, row in enumerate(existing_rows, start=2)}
    inserted = 0
    updated = 0
    for row in rows:
        key = row_key(row, key_columns)
        if key in existing_keys:
            row_number = existing_keys[key]
            updated += 1
        else:
            row_number = 2 + len(existing_rows) + inserted
            inserted += 1
        write_values(
            service,
            spreadsheet_id,
            f"{quote_sheet(sheet)}!A{row_number}:{column_letter(len(columns))}{row_number}",
            [row_to_values(row, columns)],
        )
    return {"inserted": inserted, "updated": updated}


def append_row(service: Any, spreadsheet_id: str, sheet: str, columns: list[str], row: dict[str, Any]) -> None:
    existing_values = read_values(service, spreadsheet_id, sheet, 1, max(len(columns), 30))
    next_row = max(2, 1 + len(existing_values))
    write_values(
        service,
        spreadsheet_id,
        f"{quote_sheet(sheet)}!A{next_row}:{column_letter(len(columns))}{next_row}",
        [row_to_values(row, columns)],
    )


def ensure_ledger_tabs(service: Any, spreadsheet_id: str) -> None:
    for sheet, columns in LEDGER_TABS.items():
        ensure_header(service, spreadsheet_id, sheet, columns, preserve_existing=True)


def build_dashboard_tgs_row(summary: ScoreSummary, updated_at: str) -> dict[str, Any]:
    return {
        "date": summary.as_of,
        "strategy": STRATEGY_NAME,
        "market": MARKET_NAME,
        "signal_count": summary.signal_count,
        "trade_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "win_rate": "",
        "pnl": 0,
        "profit_factor": "",
        "max_drawdown": "",
        "status": summary.status,
        "source_file": summary.source_file,
        "note": summary.note,
        "updated_at": updated_at,
    }


def build_dashboard_home_rows(summary: ScoreSummary, updated_at: str) -> list[dict[str, Any]]:
    return [
        home_row("TGS Daily Score Check Status", summary.status, status_color(summary.status), updated_at, ""),
        home_row("TGS Latest Score Check Date", summary.as_of, "gray", updated_at, ""),
        home_row("TGS Signal Count", summary.signal_count, status_color(summary.status), updated_at, "stable_score >= 90"),
        home_row("TGS Max Score Ticker", summary.max_score_ticker or "No Data", "gray", updated_at, f"max_score={format_number(summary.max_score)}"),
        home_row("TGS Paper Open Positions", 0, "gray", updated_at, "Cloud Phase 1: score check only."),
        home_row("TGS Paper Equity", "No Data", "gray", updated_at, "Cloud Phase 1: pending/register not enabled."),
        home_row("TGS Last Updated", updated_at, "gray", updated_at, ""),
    ]


def home_row(metric: str, value: Any, status: str, updated_at: str, note: str) -> dict[str, Any]:
    return {
        "section": "TGS",
        "metric": metric,
        "value": value,
        "status": status,
        "updated_at": updated_at,
        "note": note,
    }


def status_color(status: str) -> str:
    if status == "signal_detected":
        return "yellow"
    if status == "no_signal":
        return "green"
    return "gray"


def build_dashboard_log_row(summary: ScoreSummary, updated_at: str, rid: str) -> dict[str, Any]:
    return {
        "timestamp": updated_at,
        "run_id": rid,
        "script": "stable_cloud_score_check.py",
        "action": "daily_score_check",
        "status": "success",
        "rows_read": summary.rows_scored,
        "rows_written": summary.rows_scored + 9,
        "target_sheet": "TGS, Home, Log",
        "source_file": summary.source_file,
        "error_message": "",
        "project": "TGS",
        "event_type": "cloud_daily_score_check",
        "summary": "TGS Stable Cloud Daily Score Check",
        "result": f"signal_count={summary.signal_count}; max_score={format_number(summary.max_score)}; status={summary.status}",
        "next_action": "Review Signal" if summary.signal_count else "Monitor",
    }


def build_run_log_row(
    summary: ScoreSummary,
    updated_at: str,
    rid: str,
    mode: str,
    ledger_spreadsheet_id: str,
    dashboard_spreadsheet_id: str,
    status: str = "success",
    error_message: str = "",
) -> dict[str, Any]:
    return {
        "timestamp": updated_at,
        "run_id": rid,
        "script": "stable_cloud_score_check.py",
        "mode": mode,
        "status": status,
        "as_of": summary.as_of,
        "rows_scored": summary.rows_scored,
        "signal_count": summary.signal_count,
        "max_score_ticker": summary.max_score_ticker,
        "max_score": format_number(summary.max_score),
        "ledger_spreadsheet_id": ledger_spreadsheet_id,
        "dashboard_spreadsheet_id": dashboard_spreadsheet_id,
        "error_message": error_message,
    }


def update_ledger_sheet(
    service: Any,
    spreadsheet_id: str,
    dashboard_spreadsheet_id: str,
    rows: list[dict[str, Any]],
    summary: ScoreSummary,
    updated_at: str,
    rid: str,
) -> dict[str, Any]:
    ensure_ledger_tabs(service, spreadsheet_id)
    score_result = upsert_rows(
        service,
        spreadsheet_id,
        "TGS_Daily_Score_Check",
        REPORT_COLUMNS,
        rows,
        ["date", "ticker"],
    )
    append_row(
        service,
        spreadsheet_id,
        "TGS_Run_Log",
        RUN_LOG_COLUMNS,
        build_run_log_row(summary, updated_at, rid, "execute", spreadsheet_id, dashboard_spreadsheet_id),
    )
    return {"score": score_result, "run_log": {"inserted": 1}}


def update_dashboard_sheet(
    service: Any,
    spreadsheet_id: str,
    summary: ScoreSummary,
    updated_at: str,
    rid: str,
) -> dict[str, Any]:
    tgs_header = ensure_header(service, spreadsheet_id, "TGS", TGS_COLUMNS, preserve_existing=False)
    home_header = ensure_header(service, spreadsheet_id, "Home", HOME_COLUMNS, preserve_existing=False)
    log_header = ensure_header(service, spreadsheet_id, "Log", LOG_COLUMNS, preserve_existing=True)
    tgs_result = upsert_rows(
        service,
        spreadsheet_id,
        "TGS",
        tgs_header,
        [build_dashboard_tgs_row(summary, updated_at)],
        ["date", "strategy", "market"],
    )
    home_result = upsert_rows(
        service,
        spreadsheet_id,
        "Home",
        home_header,
        build_dashboard_home_rows(summary, updated_at),
        ["section", "metric"],
    )
    append_row(service, spreadsheet_id, "Log", log_header, build_dashboard_log_row(summary, updated_at, rid))
    return {"tgs": tgs_result, "home": home_result, "log": {"inserted": 1}}


def latest_row(values: list[list[Any]], columns: list[str]) -> dict[str, Any]:
    if len(values) <= 1:
        return {}
    return values_to_rows([values[-1]], columns)[0]


def verify_sheet_state(service: Any, ledger_spreadsheet_id: str, dashboard_spreadsheet_id: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ledger_spreadsheet_id": ledger_spreadsheet_id,
        "dashboard_spreadsheet_id": dashboard_spreadsheet_id,
    }
    if ledger_spreadsheet_id:
        ledger_meta = service.spreadsheets().get(
            spreadsheetId=ledger_spreadsheet_id,
            fields="spreadsheetId,spreadsheetUrl,properties.title,sheets.properties.title",
        ).execute()
        ledger_titles = [item["properties"]["title"] for item in ledger_meta.get("sheets", [])]
        score_values = read_values_optional(service, ledger_spreadsheet_id, "TGS_Daily_Score_Check", 1, len(REPORT_COLUMNS))
        run_values = read_values_optional(service, ledger_spreadsheet_id, "TGS_Run_Log", 1, len(RUN_LOG_COLUMNS))
        score_rows = values_to_rows(score_values[1:], REPORT_COLUMNS) if len(score_values) > 1 else []
        latest_score_date = max((str(row.get("date", "")) for row in score_rows), default="")
        latest_score_rows = [row for row in score_rows if str(row.get("date", "")) == latest_score_date]
        result["ledger"] = {
            "title": ledger_meta.get("properties", {}).get("title", ""),
            "url": ledger_meta.get("spreadsheetUrl", ""),
            "required_tabs_present": all(tab in ledger_titles for tab in LEDGER_TABS),
            "missing_tabs": [tab for tab in LEDGER_TABS if tab not in ledger_titles],
            "daily_score_rows": len(score_rows),
            "latest_score_date": latest_score_date,
            "latest_score_row_count": len(latest_score_rows),
            "latest_signal_count": sum(1 for row in latest_score_rows if (safe_float(row.get("stable_score")) or 0.0) >= SCORE_THRESHOLD),
            "latest_run_log_row": latest_row(run_values, RUN_LOG_COLUMNS),
        }
    if dashboard_spreadsheet_id:
        dashboard_meta = service.spreadsheets().get(
            spreadsheetId=dashboard_spreadsheet_id,
            fields="spreadsheetId,spreadsheetUrl,properties.title,sheets.properties.title",
        ).execute()
        tgs_values = read_values_optional(service, dashboard_spreadsheet_id, "TGS", 1, len(TGS_COLUMNS))
        home_values = read_values_optional(service, dashboard_spreadsheet_id, "Home", 1, len(HOME_COLUMNS))
        log_values = read_values_optional(service, dashboard_spreadsheet_id, "Log", 1, len(LOG_COLUMNS))
        home_rows = values_to_rows(home_values[1:], HOME_COLUMNS) if len(home_values) > 1 else []
        result["dashboard"] = {
            "title": dashboard_meta.get("properties", {}).get("title", ""),
            "url": dashboard_meta.get("spreadsheetUrl", ""),
            "latest_tgs_row": latest_row(tgs_values, TGS_COLUMNS),
            "latest_tgs_home_rows": [row for row in home_rows if row.get("section") == "TGS"][-7:],
            "latest_log_row": latest_row(log_values, LOG_COLUMNS),
        }
    return result


def write_dry_run(args: argparse.Namespace, rows: list[dict[str, Any]], summary: ScoreSummary, updated_at: str, rid: str) -> Path:
    out_dir = args.out_dir / updated_at.replace("-", "").replace(":", "").replace(" ", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / summary.source_file, REPORT_COLUMNS, rows)
    write_csv(out_dir / "dashboard_tgs_preview.csv", TGS_COLUMNS, [build_dashboard_tgs_row(summary, updated_at)])
    write_csv(out_dir / "dashboard_home_preview.csv", HOME_COLUMNS, build_dashboard_home_rows(summary, updated_at))
    write_csv(out_dir / "run_log_preview.csv", RUN_LOG_COLUMNS, [build_run_log_row(summary, updated_at, rid, "dry_run", args.ledger_spreadsheet_id, args.dashboard_spreadsheet_id)])
    payload = {
        "mode": "dry_run" if not args.execute else "execute",
        "run_id": rid,
        "updated_at": updated_at,
        "summary": summary.__dict__,
        "rules": {
            "score_threshold": SCORE_THRESHOLD,
            "stop_loss_pct": STOP_LOSS_PCT,
            "take_profit_pct": TAKE_PROFIT_PCT,
            "max_holding_days": MAX_HOLDING_DAYS,
            "paper_trading_only": True,
            "pending_registration_enabled": False,
            "real_trading_enabled": False,
        },
    }
    (out_dir / "payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_dir


def main() -> int:
    args = parse_args()
    as_of = parse_as_of(args.as_of)
    updated_at = now_jst()
    rid = run_id(updated_at)
    mode = "execute" if args.execute else "dry_run"

    try:
        if args.verify_only:
            service = build_sheets_service()
            print(json.dumps(verify_sheet_state(service, args.ledger_spreadsheet_id, args.dashboard_spreadsheet_id), ensure_ascii=False, indent=2))
            return 0

        if args.init_only:
            if not args.execute:
                print(json.dumps({"ok": True, "mode": "dry_run", "message": "init-only requires --execute to write Sheets"}, ensure_ascii=False, indent=2))
                return 0
            if not args.ledger_spreadsheet_id:
                raise RuntimeError("Missing GOOGLE_SHEETS_SPREADSHEET_ID.")
            service = build_sheets_service()
            ensure_ledger_tabs(service, args.ledger_spreadsheet_id)
            print(json.dumps({"ok": True, "mode": "execute", "initialized_tabs": list(LEDGER_TABS)}, ensure_ascii=False, indent=2))
            return 0

        rows = build_score_rows(as_of, args.metadata, updated_at)
        source_file = f"stable_daily_score_check_{as_of.strftime('%Y_%m_%d')}.csv"
        summary = score_summary(rows, source_file)
        dry_run_dir = write_dry_run(args, rows, summary, updated_at, rid)
        result: dict[str, Any] = {
            "ok": True,
            "mode": mode,
            "run_id": rid,
            "dry_run_dir": str(dry_run_dir),
            "summary": summary.__dict__,
            "pending_registration_enabled": False,
            "real_trading_enabled": False,
            "executed": False,
        }
        if args.execute:
            if not args.ledger_spreadsheet_id:
                raise RuntimeError("Missing GOOGLE_SHEETS_SPREADSHEET_ID.")
            service = build_sheets_service()
            result["ledger_update"] = update_ledger_sheet(
                service,
                args.ledger_spreadsheet_id,
                args.dashboard_spreadsheet_id,
                rows,
                summary,
                updated_at,
                rid,
            )
            if args.dashboard_spreadsheet_id and not args.skip_dashboard:
                result["dashboard_update"] = update_dashboard_sheet(
                    service,
                    args.dashboard_spreadsheet_id,
                    summary,
                    updated_at,
                    rid,
                )
            else:
                result["dashboard_update"] = {"skipped": True, "reason": "dashboard_spreadsheet_id_not_set_or_skipped"}
            result["executed"] = True
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "mode": mode, "run_id": rid, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
