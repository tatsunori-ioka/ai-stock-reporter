from __future__ import annotations

import argparse
import csv
import os
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import yfinance as yf


JST = timezone(timedelta(hours=9))
RULE_VERSION = "TGS Stable Ver1.0 Paper"
INITIAL_CAPITAL = float(os.getenv("STABLE_INITIAL_CAPITAL", "3000000"))
POSITION_SIZE = float(os.getenv("STABLE_POSITION_SIZE", "500000"))
MAX_POSITIONS = int(os.getenv("STABLE_MAX_POSITIONS", "6"))
STOP_LOSS_PCT = -0.10
TAKE_PROFIT_PCT = 0.30
MAX_HOLDING_DAYS = 60

BASE_DIR = Path(os.getenv("STABLE_DATA_DIR", "/data"))
if not BASE_DIR.exists():
    BASE_DIR = Path(os.getenv("STABLE_DATA_DIR_FALLBACK", "outputs"))

PENDING_PATH = Path(os.getenv("STABLE_PAPER_PENDING_PATH", str(BASE_DIR / "stable_paper_pending_orders.csv")))
POSITIONS_PATH = Path(os.getenv("STABLE_PAPER_POSITIONS_PATH", str(BASE_DIR / "stable_paper_positions.csv")))
TRADE_HISTORY_PATH = Path(os.getenv("STABLE_PAPER_TRADE_HISTORY_PATH", str(BASE_DIR / "stable_paper_trade_history.csv")))
ACCOUNT_PATH = Path(os.getenv("STABLE_PAPER_ACCOUNT_PATH", str(BASE_DIR / "stable_paper_account.csv")))
DAILY_LOG_PATH = Path(os.getenv("STABLE_PAPER_DAILY_LOG_PATH", str(BASE_DIR / "stable_paper_daily_log.csv")))

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
DAILY_COLUMNS = [
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


def read_rows(path: Path, columns: list[str]) -> list[dict[str, str]]:
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


def append_rows(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def next_id(prefix: str, rows: list[dict[str, str]], key: str) -> str:
    numbers: list[int] = []
    for row in rows:
        value = row.get(key, "")
        if value.startswith(prefix):
            try:
                numbers.append(int(value.replace(prefix, "")))
            except ValueError:
                pass
    return f"{prefix}{max(numbers, default=0) + 1:06d}"


def latest_account() -> dict[str, Any]:
    rows = read_rows(ACCOUNT_PATH, ACCOUNT_COLUMNS)
    if rows:
        return rows[-1]
    return {
        "as_of": "",
        "cash": INITIAL_CAPITAL,
        "initial_capital": INITIAL_CAPITAL,
        "realized_pnl": 0.0,
        "open_positions": 0,
        "pending_orders": 0,
        "market_value": 0.0,
        "equity": INITIAL_CAPITAL,
    }


def ticker_frame(downloaded: Any, ticker: str):
    if downloaded is None or getattr(downloaded, "empty", True):
        return None
    if hasattr(downloaded.columns, "levels"):
        if ticker not in downloaded.columns.get_level_values(0):
            return None
        frame = downloaded[ticker].dropna(how="all")
    else:
        frame = downloaded.dropna(how="all")
    return None if frame.empty else frame


def latest_bar(downloaded: Any, ticker: str, as_of: date) -> dict[str, float] | None:
    frame = ticker_frame(downloaded, ticker)
    if frame is None:
        return None
    frame = frame[frame.index.date <= as_of]
    if frame.empty:
        return None
    row = frame.iloc[-1]
    return {
        "date": frame.index[-1].date().isoformat(),
        "open": safe_float(row.get("Open")),
        "high": safe_float(row.get("High")),
        "low": safe_float(row.get("Low")),
        "close": safe_float(row.get("Close")),
    }


def holding_days(downloaded: Any, ticker: str, entry_date: str, as_of: date) -> int:
    frame = ticker_frame(downloaded, ticker)
    entry = parse_date(entry_date)
    if frame is None or entry is None:
        return 0
    frame = frame[(frame.index.date >= entry) & (frame.index.date <= as_of)]
    return int(len(frame))


def daily_row(as_of: date, **values: Any) -> dict[str, Any]:
    row = {column: "" for column in DAILY_COLUMNS}
    row["report_date"] = as_of.isoformat()
    row.update(values)
    return row


def execute_pending(
    pending_rows: list[dict[str, str]],
    positions: list[dict[str, str]],
    trades: list[dict[str, str]],
    downloaded: Any,
    as_of: date,
    cash: float,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, Any]], float]:
    remaining: list[dict[str, str]] = []
    daily: list[dict[str, Any]] = []
    open_tickers = {row.get("ticker", "") for row in positions}

    for pending in pending_rows:
        signal_date = parse_date(pending.get("signal_date", ""))
        if pending.get("status") not in ("", "pending", "waiting_capacity", "waiting_price"):
            remaining.append(pending)
            continue
        if signal_date is None or signal_date >= as_of:
            remaining.append(pending)
            continue
        if pending.get("ticker") in open_tickers:
            pending["status"] = "skipped_already_held"
            continue
        if len(positions) >= MAX_POSITIONS or cash < POSITION_SIZE:
            pending["status"] = "waiting_capacity"
            remaining.append(pending)
            continue

        bar = latest_bar(downloaded, pending["ticker"], as_of)
        if not bar or bar["date"] != as_of.isoformat() or bar["open"] <= 0:
            pending["status"] = "waiting_price"
            remaining.append(pending)
            continue

        trade_id = next_id("PT", positions + trades, "paper_trade_id")
        entry_price = bar["open"]
        shares = POSITION_SIZE / entry_price
        position = {
            "paper_trade_id": trade_id,
            "ticker": pending["ticker"],
            "name": pending.get("name", ""),
            "sector": pending.get("sector", ""),
            "signal_date": pending.get("signal_date", ""),
            "entry_date": as_of.isoformat(),
            "entry_price": round(entry_price, 4),
            "shares": round(shares, 8),
            "allocation": POSITION_SIZE,
            "stop_price": round(entry_price * (1 + STOP_LOSS_PCT), 4),
            "take_profit_price": round(entry_price * (1 + TAKE_PROFIT_PCT), 4),
            "max_holding_days": MAX_HOLDING_DAYS,
            "status": "open",
        }
        positions.append(position)
        cash -= POSITION_SIZE
        open_tickers.add(pending["ticker"])
        trades.append(
            {
                "timestamp": datetime.now(JST).isoformat(timespec="seconds"),
                "paper_trade_id": trade_id,
                "side": "BUY",
                "ticker": pending["ticker"],
                "name": pending.get("name", ""),
                "sector": pending.get("sector", ""),
                "price": round(entry_price, 4),
                "shares": round(shares, 8),
                "cash_amount": round(-POSITION_SIZE, 2),
                "reason": "next_trading_day_open",
                "pnl": 0.0,
                "return_pct": 0.0,
                "signal_date": pending.get("signal_date", ""),
                "entry_date": as_of.isoformat(),
                "exit_date": "",
                "rule_version": RULE_VERSION,
            }
        )
        daily.append(
            daily_row(
                as_of,
                row_type="paper_buy",
                ticker=pending["ticker"],
                name=pending.get("name", ""),
                sector=pending.get("sector", ""),
                action="BUY",
                reason="next_trading_day_open",
                status="executed",
                signal_date=pending.get("signal_date", ""),
                entry_date=as_of.isoformat(),
                entry_price=round(entry_price, 4),
                open=bar["open"],
                high=bar["high"],
                low=bar["low"],
                close=bar["close"],
                stop_price=position["stop_price"],
                take_profit_price=position["take_profit_price"],
                shares=round(shares, 8),
                paper_trade_id=trade_id,
                pending_order_id=pending.get("pending_order_id", ""),
                notes="Paper trade only. No real order sent.",
            )
        )

    return remaining, positions, daily, cash


def process_positions(
    positions: list[dict[str, str]],
    trades: list[dict[str, str]],
    downloaded: Any,
    as_of: date,
    cash: float,
    realized_pnl: float,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], float, float, float]:
    remaining: list[dict[str, str]] = []
    daily: list[dict[str, Any]] = []
    market_value_total = 0.0

    for position in positions:
        bar = latest_bar(downloaded, position["ticker"], as_of)
        if not bar:
            remaining.append(position)
            daily.append(
                daily_row(
                    as_of,
                    row_type="holding",
                    ticker=position["ticker"],
                    name=position.get("name", ""),
                    sector=position.get("sector", ""),
                    action="HOLD",
                    reason="missing_price",
                    status="open",
                    entry_date=position.get("entry_date", ""),
                    paper_trade_id=position.get("paper_trade_id", ""),
                    notes="Price data missing. Position kept open.",
                )
            )
            continue

        entry_price = safe_float(position.get("entry_price"))
        shares = safe_float(position.get("shares"))
        allocation = safe_float(position.get("allocation"), POSITION_SIZE)
        stop_price = safe_float(position.get("stop_price"))
        take_profit_price = safe_float(position.get("take_profit_price"))
        days = holding_days(downloaded, position["ticker"], position.get("entry_date", ""), as_of)
        close_value = shares * bar["close"]
        market_value_total += close_value

        exit_reason = ""
        exit_price = 0.0
        row_type = "holding"
        if bar["low"] <= stop_price:
            exit_reason = "stop_loss"
            exit_price = stop_price
            row_type = "stop_loss_exit"
        elif bar["high"] >= take_profit_price:
            exit_reason = "take_profit"
            exit_price = take_profit_price
            row_type = "take_profit_exit"
        elif days >= MAX_HOLDING_DAYS:
            exit_reason = "max_holding"
            exit_price = bar["close"]
            row_type = "max_holding_exit"

        if exit_reason:
            exit_value = shares * exit_price
            pnl = exit_value - allocation
            return_pct = exit_price / entry_price - 1 if entry_price else 0.0
            cash += exit_value
            realized_pnl += pnl
            market_value_total -= close_value
            trades.append(
                {
                    "timestamp": datetime.now(JST).isoformat(timespec="seconds"),
                    "paper_trade_id": position.get("paper_trade_id", ""),
                    "side": "SELL",
                    "ticker": position["ticker"],
                    "name": position.get("name", ""),
                    "sector": position.get("sector", ""),
                    "price": round(exit_price, 4),
                    "shares": round(shares, 8),
                    "cash_amount": round(exit_value, 2),
                    "reason": exit_reason,
                    "pnl": round(pnl, 2),
                    "return_pct": round(return_pct, 6),
                    "signal_date": position.get("signal_date", ""),
                    "entry_date": position.get("entry_date", ""),
                    "exit_date": as_of.isoformat(),
                    "rule_version": RULE_VERSION,
                }
            )
            daily.append(
                daily_row(
                    as_of,
                    row_type=row_type,
                    ticker=position["ticker"],
                    name=position.get("name", ""),
                    sector=position.get("sector", ""),
                    action="SELL",
                    reason=exit_reason,
                    status="closed",
                    signal_date=position.get("signal_date", ""),
                    entry_date=position.get("entry_date", ""),
                    entry_price=round(entry_price, 4),
                    open=bar["open"],
                    high=bar["high"],
                    low=bar["low"],
                    close=bar["close"],
                    stop_price=stop_price,
                    take_profit_price=take_profit_price,
                    holding_days=days,
                    shares=round(shares, 8),
                    market_value=round(exit_value, 2),
                    unrealized_return_pct=round(return_pct, 6),
                    realized_pnl=round(pnl, 2),
                    paper_trade_id=position.get("paper_trade_id", ""),
                    notes="Paper trade only. No real order sent.",
                )
            )
        else:
            unrealized = bar["close"] / entry_price - 1 if entry_price else 0.0
            remaining.append(position)
            daily.append(
                daily_row(
                    as_of,
                    row_type="holding",
                    ticker=position["ticker"],
                    name=position.get("name", ""),
                    sector=position.get("sector", ""),
                    action="HOLD",
                    reason="no_exit",
                    status="open",
                    signal_date=position.get("signal_date", ""),
                    entry_date=position.get("entry_date", ""),
                    entry_price=round(entry_price, 4),
                    open=bar["open"],
                    high=bar["high"],
                    low=bar["low"],
                    close=bar["close"],
                    stop_price=stop_price,
                    take_profit_price=take_profit_price,
                    holding_days=days,
                    shares=round(shares, 8),
                    market_value=round(close_value, 2),
                    unrealized_return_pct=round(unrealized, 6),
                    paper_trade_id=position.get("paper_trade_id", ""),
                )
            )

    return remaining, daily, cash, realized_pnl, market_value_total


def run_daily(as_of: date | None = None) -> dict[str, Any]:
    as_of = as_of or datetime.now(JST).date()
    pending = read_rows(PENDING_PATH, PENDING_COLUMNS)
    positions = read_rows(POSITIONS_PATH, POSITION_COLUMNS)
    trades = read_rows(TRADE_HISTORY_PATH, TRADE_COLUMNS)
    account = latest_account()
    cash = safe_float(account.get("cash"), INITIAL_CAPITAL)
    realized_pnl = safe_float(account.get("realized_pnl"), 0.0)

    tickers = sorted({row.get("ticker", "") for row in pending + positions if row.get("ticker")})
    downloaded = None
    if tickers:
        start = (as_of - timedelta(days=450)).isoformat()
        end = (as_of + timedelta(days=1)).isoformat()
        downloaded = yf.download(tickers, start=start, end=end, auto_adjust=False, group_by="ticker", threads=True, progress=False)

    pending, positions, buy_daily, cash = execute_pending(pending, positions, trades, downloaded, as_of, cash)
    positions, position_daily, cash, realized_pnl, market_value = process_positions(
        positions, trades, downloaded, as_of, cash, realized_pnl
    )
    daily = buy_daily + position_daily
    if not daily:
        daily.append(
            daily_row(
                as_of,
                row_type="daily_summary",
                action="NONE",
                reason="no_pending_or_positions",
                status="no_action",
                notes="Paper trading daily job ran. No real orders were sent.",
            )
        )

    equity = cash + market_value
    account_row = {
        "as_of": as_of.isoformat(),
        "cash": round(cash, 2),
        "initial_capital": INITIAL_CAPITAL,
        "realized_pnl": round(realized_pnl, 2),
        "open_positions": len(positions),
        "pending_orders": len(pending),
        "market_value": round(market_value, 2),
        "equity": round(equity, 2),
    }

    write_rows(PENDING_PATH, PENDING_COLUMNS, pending)
    write_rows(POSITIONS_PATH, POSITION_COLUMNS, positions)
    write_rows(TRADE_HISTORY_PATH, TRADE_COLUMNS, trades)
    write_rows(ACCOUNT_PATH, ACCOUNT_COLUMNS, [account_row])
    append_rows(DAILY_LOG_PATH, DAILY_COLUMNS, daily)
    write_rows(BASE_DIR / f"stable_paper_daily_{as_of.isoformat()}.csv", DAILY_COLUMNS, daily)

    return {
        "ok": True,
        "as_of": as_of.isoformat(),
        "pending_orders": len(pending),
        "open_positions": len(positions),
        "trade_history_rows": len(trades),
        "daily_rows": len(daily),
        "cash": round(cash, 2),
        "market_value": round(market_value, 2),
        "equity": round(equity, 2),
        "paper_trading_only": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TGS Stable Ver1.0 paper trading daily job.")
    parser.add_argument("--as-of", default=date.today().isoformat())
    args = parser.parse_args()
    result = run_daily(parse_date(args.as_of))
    print(result)


if __name__ == "__main__":
    main()
