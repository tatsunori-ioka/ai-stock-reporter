from __future__ import annotations

import csv
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


JST = timezone(timedelta(hours=9))
RULE_VERSION = "stable-1.0"
SIGNAL_TYPE = "tgs_stable_v1_signal"
THRESHOLD = 90
LINE_BROADCAST_ENDPOINT = "https://api.line.me/v2/bot/message/broadcast"
MAC_PENDING_WEBHOOK_URL = os.getenv("STABLE_MAC_PENDING_WEBHOOK_URL", "")
MAC_PENDING_WEBHOOK_TOKEN = os.getenv("STABLE_MAC_PENDING_WEBHOOK_TOKEN", "")

BASE_DIR = Path(os.getenv("STABLE_DATA_DIR", "/data"))
if not BASE_DIR.exists():
    BASE_DIR = Path(os.getenv("STABLE_DATA_DIR_FALLBACK", "outputs"))

METADATA_PATH = Path(os.getenv("STABLE_METADATA_PATH", "stable_universe_metadata.csv"))
ALERT_LOG_PATH = Path(os.getenv("STABLE_ALERT_LOG_PATH", str(BASE_DIR / "stable_scanner_alert_log.csv")))
PAPER_PENDING_PATH = Path(os.getenv("STABLE_PAPER_PENDING_PATH", str(BASE_DIR / "stable_paper_pending_orders.csv")))

STRONG_SECTORS = {
    "Trading companies",
    "Machinery",
    "Nonferrous metals",
    "Real estate",
    "Shipbuilding",
}

ALERT_LOG_COLUMNS = [
    "received_at",
    "signal_date",
    "ticker",
    "exchange",
    "price",
    "stable_score_payload",
    "stable_score_recomputed",
    "validation_status",
    "validation_reason",
    "line_sent",
    "line_error",
    "mac_pending_sent",
    "mac_pending_error",
    "paper_pending_created",
    "paper_pending_id",
    "dedup_key",
    "raw_payload",
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


def normalize_ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper()
    if ticker.endswith(".T"):
        return ticker
    if ticker.isdigit():
        return f"{ticker}.T"
    return ticker


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "y", "above", "gc"}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def append_row(path: Path, columns: list[str], row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        if not exists:
            writer.writeheader()
        writer.writerow({column: row.get(column, "") for column in columns})


def load_metadata() -> dict[str, dict[str, str]]:
    rows = read_rows(METADATA_PATH)
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        ticker = normalize_ticker(row.get("ticker"))
        if ticker:
            result[ticker] = row
    return result


def recompute_stable_score(payload: dict[str, Any]) -> int:
    score = 0
    score += 30 if normalize_bool(payload.get("weekly_above_200ma")) else 0
    score += 30 if normalize_bool(payload.get("weekly_macd_gc")) else 0
    score += 20 if normalize_bool(payload.get("weekly_macd_uptrend")) else 0
    score += 20 if normalize_bool(payload.get("daily_rsi_40_65")) else 0
    score += 20 if normalize_bool(payload.get("daily_volume_1_5x")) else 0
    return score


def signal_date(payload: dict[str, Any], received_at: datetime) -> str:
    for key in ("signal_date", "date", "bar_date", "time"):
        value = str(payload.get(key, "")).strip()
        if value:
            return value[:10]
    return received_at.date().isoformat()


def dedup_key(ticker: str, date_text: str) -> str:
    return f"{RULE_VERSION}:{ticker}:{date_text}"


def accepted_dedup_keys() -> set[str]:
    return {
        row.get("dedup_key", "")
        for row in read_rows(ALERT_LOG_PATH)
        if row.get("validation_status") == "accepted"
    }


def next_pending_id() -> str:
    numbers = []
    for row in read_rows(PAPER_PENDING_PATH):
        value = row.get("pending_order_id", "")
        if value.startswith("PO"):
            try:
                numbers.append(int(value.replace("PO", "")))
            except ValueError:
                pass
    return f"PO{max(numbers, default=0) + 1:06d}"


def validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    received_at = datetime.now(JST)
    ticker = normalize_ticker(payload.get("ticker"))
    date_text = signal_date(payload, received_at)
    key = dedup_key(ticker, date_text)
    score_payload = safe_float(payload.get("stable_score"), safe_float(payload.get("score"), 0.0))
    score_recomputed = recompute_stable_score(payload)
    metadata = load_metadata()
    meta = metadata.get(ticker)

    result = {
        "received_at": received_at.isoformat(timespec="seconds"),
        "ticker": ticker,
        "signal_date": date_text,
        "dedup_key": key,
        "stable_score_payload": score_payload,
        "stable_score_recomputed": score_recomputed,
        "metadata": meta,
        "accepted": False,
        "reason": "",
    }

    checks = [
        (payload.get("system") == "TGS", "invalid_system"),
        (payload.get("type") == SIGNAL_TYPE, "invalid_type"),
        (payload.get("version") == RULE_VERSION, "invalid_version"),
        (bool(ticker), "missing_ticker"),
        (score_payload >= THRESHOLD, "payload_score_below_90"),
        (score_recomputed >= THRESHOLD, "recomputed_score_below_90"),
        (meta is not None, "ticker_not_in_stable_universe"),
    ]
    for ok, reason in checks:
        if not ok:
            result["reason"] = reason
            return result

    if meta.get("market_cap_bucket") != "Large":
        result["reason"] = "not_large_cap"
        return result
    if meta.get("sector") not in STRONG_SECTORS:
        result["reason"] = "not_strong_sector"
        return result
    if key in accepted_dedup_keys():
        result["reason"] = "duplicate_signal"
        return result

    result["accepted"] = True
    result["reason"] = "accepted"
    return result


def build_line_message(payload: dict[str, Any], validation: dict[str, Any]) -> str:
    meta = validation.get("metadata") or {}
    return "\n".join(
        [
            "TGS Stable Ver1.0 Signal",
            "",
            f"Ticker: {validation['ticker']}",
            f"Name: {meta.get('name', '')}",
            f"Score: {validation['stable_score_recomputed']}",
            f"Price: {payload.get('price') or payload.get('close', '')}",
            f"RSI: {payload.get('daily_rsi', '')}",
            f"Volume Ratio: {payload.get('volume_ratio', '')}",
            "",
            "Entry: Next trading day open",
            "Stop: -10%",
            "Take Profit: +30%",
            "Max Holding: 60 trading days",
            "",
            "Paper Trading Mode: record only",
        ]
    )


def send_line(message: str) -> tuple[bool, str]:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        return False, "LINE_CHANNEL_ACCESS_TOKEN_not_set"
    payload = {"messages": [{"type": "text", "text": message}]}
    request = urllib.request.Request(
        LINE_BROADCAST_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status >= 300:
                return False, f"line_http_{response.status}"
    except urllib.error.URLError as exc:
        return False, str(exc)
    return True, ""


def forward_to_mac_pending(payload: dict[str, Any], validation: dict[str, Any]) -> tuple[bool, str]:
    if not MAC_PENDING_WEBHOOK_URL:
        return False, "STABLE_MAC_PENDING_WEBHOOK_URL_not_set"
    body = {
        "ticker": validation["ticker"],
        "signal_date": validation["signal_date"],
        "stable_score": validation["stable_score_recomputed"],
        "daily_rsi": payload.get("daily_rsi", ""),
        "volume_ratio": payload.get("volume_ratio", ""),
        "source": "render_stable_webhook",
        "paper_trading_only": True,
    }
    headers = {"Content-Type": "application/json"}
    if MAC_PENDING_WEBHOOK_TOKEN:
        headers["X-Stable-Pending-Token"] = MAC_PENDING_WEBHOOK_TOKEN
    request = urllib.request.Request(
        MAC_PENDING_WEBHOOK_URL,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8")
            if response.status >= 300:
                return False, f"mac_pending_http_{response.status}:{response_body}"
    except urllib.error.URLError as exc:
        return False, str(exc)
    return True, ""


def append_pending(payload: dict[str, Any], validation: dict[str, Any]) -> tuple[bool, str]:
    ticker = validation["ticker"]
    date_text = validation["signal_date"]
    for row in read_rows(PAPER_PENDING_PATH):
        if row.get("ticker") == ticker and row.get("signal_date") == date_text:
            return False, row.get("pending_order_id", "")
    pending_id = next_pending_id()
    meta = validation.get("metadata") or {}
    append_row(
        PAPER_PENDING_PATH,
        PENDING_COLUMNS,
        {
            "pending_order_id": pending_id,
            "signal_date": date_text,
            "ticker": ticker,
            "name": meta.get("name", ""),
            "sector": meta.get("sector", ""),
            "tgs_score": validation["stable_score_recomputed"],
            "daily_rsi": payload.get("daily_rsi", ""),
            "volume_ratio": payload.get("volume_ratio", ""),
            "planned_entry": "next_trading_day_open",
            "status": "pending",
        },
    )
    return True, pending_id


def process_stable_webhook(payload: dict[str, Any], send_line_enabled: bool = True) -> dict[str, Any]:
    validation = validate_payload(payload)
    line_sent = False
    line_error = ""
    mac_pending_sent = False
    mac_pending_error = ""
    pending_created = False
    pending_id = ""

    if validation["accepted"]:
        pending_created, pending_id = append_pending(payload, validation)
        mac_pending_sent, mac_pending_error = forward_to_mac_pending(payload, validation)
        if send_line_enabled:
            line_sent, line_error = send_line(build_line_message(payload, validation))
        else:
            line_error = "line_disabled"

    append_row(
        ALERT_LOG_PATH,
        ALERT_LOG_COLUMNS,
        {
            "received_at": validation["received_at"],
            "signal_date": validation["signal_date"],
            "ticker": validation["ticker"],
            "exchange": payload.get("exchange", ""),
            "price": payload.get("price") or payload.get("close", ""),
            "stable_score_payload": validation["stable_score_payload"],
            "stable_score_recomputed": validation["stable_score_recomputed"],
            "validation_status": "accepted" if validation["accepted"] else "rejected",
            "validation_reason": validation["reason"],
            "line_sent": line_sent,
            "line_error": line_error,
            "mac_pending_sent": mac_pending_sent,
            "mac_pending_error": mac_pending_error,
            "paper_pending_created": pending_created,
            "paper_pending_id": pending_id,
            "dedup_key": validation["dedup_key"],
            "raw_payload": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    )

    return {
        "accepted": validation["accepted"],
        "reason": validation["reason"],
        "ticker": validation["ticker"],
        "signal_date": validation["signal_date"],
        "stable_score_recomputed": validation["stable_score_recomputed"],
        "line_sent": line_sent,
        "line_error": line_error,
        "paper_pending_created": pending_created,
        "paper_pending_id": pending_id,
        "mac_pending_sent": mac_pending_sent,
        "mac_pending_error": mac_pending_error,
        "dedup_key": validation["dedup_key"],
    }
