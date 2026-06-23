from __future__ import annotations

import argparse
import csv
import os
from datetime import date
from pathlib import Path
from typing import Any


BASE_DIR = Path(
    os.getenv(
        "STABLE_DATA_DIR",
        "/Users/iokatatsunori/Library/Application Support/TGSStablePaper/ledger",
    )
)
PENDING_PATH = Path(os.getenv("STABLE_PAPER_PENDING_PATH", str(BASE_DIR / "stable_paper_pending_orders.csv")))
METADATA_PATH = Path(os.getenv("STABLE_METADATA_PATH", "stable_universe_metadata.csv"))

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


def normalize_ticker(value: str) -> str:
    ticker = str(value or "").strip().upper()
    if ticker.endswith(".T"):
        return ticker
    if ticker.isdigit():
        return f"{ticker}.T"
    return ticker


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def load_metadata() -> dict[str, dict[str, str]]:
    rows = read_rows(METADATA_PATH)
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        ticker = normalize_ticker(row.get("ticker", ""))
        if ticker:
            result[ticker] = row
    return result


def next_pending_id(rows: list[dict[str, str]]) -> str:
    numbers: list[int] = []
    for row in rows:
        value = row.get("pending_order_id", "")
        if value.startswith("PO"):
            try:
                numbers.append(int(value.replace("PO", "")))
            except ValueError:
                pass
    return f"PO{max(numbers, default=0) + 1:06d}"


def add_pending_order(
    ticker: str,
    signal_date: str,
    score: str = "120",
    daily_rsi: str = "",
    volume_ratio: str = "",
    pending_path: Path = PENDING_PATH,
    metadata_path: Path = METADATA_PATH,
) -> dict[str, Any]:
    ticker = normalize_ticker(ticker)
    metadata_rows = read_rows(metadata_path)
    metadata: dict[str, dict[str, str]] = {}
    for row in metadata_rows:
        row_ticker = normalize_ticker(row.get("ticker", ""))
        if row_ticker:
            metadata[row_ticker] = row
    meta = metadata.get(ticker, {})
    rows = read_rows(pending_path)

    for row in rows:
        if row.get("ticker") == ticker and row.get("signal_date") == signal_date:
            return {
                "ok": True,
                "created": False,
                "reason": "already_pending",
                "pending_order_id": row.get("pending_order_id", ""),
                "ticker": ticker,
                "signal_date": signal_date,
                "paper_trading_only": True,
            }

    pending = {
        "pending_order_id": next_pending_id(rows),
        "signal_date": signal_date,
        "ticker": ticker,
        "name": meta.get("name", ""),
        "sector": meta.get("sector", ""),
        "tgs_score": score,
        "daily_rsi": daily_rsi,
        "volume_ratio": volume_ratio,
        "planned_entry": "next_trading_day_open",
        "status": "pending",
    }
    rows.append(pending)
    write_rows(pending_path, PENDING_COLUMNS, rows)
    return {
        "ok": True,
        "created": True,
        "reason": "created",
        "pending_order_id": pending["pending_order_id"],
        "ticker": ticker,
        "signal_date": signal_date,
        "ledger": str(pending_path),
        "paper_trading_only": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a TGS Stable Ver1.0 pending paper order.")
    parser.add_argument("--ticker", required=True, help="Ticker such as 8058.T or 8058.")
    parser.add_argument("--signal-date", default=date.today().isoformat(), help="Signal date in YYYY-MM-DD.")
    parser.add_argument("--score", default="120", help="Stable score from LINE notification.")
    parser.add_argument("--daily-rsi", default="", help="Daily RSI from LINE notification.")
    parser.add_argument("--volume-ratio", default="", help="Volume ratio from LINE notification.")
    args = parser.parse_args()

    result = add_pending_order(
        args.ticker,
        args.signal_date,
        score=args.score,
        daily_rsi=args.daily_rsi,
        volume_ratio=args.volume_ratio,
    )
    if result["created"]:
        print(f"Added pending order: {result['pending_order_id']} {result['ticker']} {result['signal_date']}")
    else:
        print(f"Already pending: {result['ticker']} {result['signal_date']} {result['pending_order_id']}")
    print(f"Ledger: {PENDING_PATH}")
    print("Paper trading only. No real order was sent.")


if __name__ == "__main__":
    main()
