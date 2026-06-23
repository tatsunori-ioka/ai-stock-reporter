from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from stable_add_pending import add_pending_order


HOST = os.getenv("STABLE_LOCAL_PENDING_HOST", "127.0.0.1")
PORT = int(os.getenv("STABLE_LOCAL_PENDING_PORT", "8765"))
TOKEN = os.getenv("STABLE_LOCAL_PENDING_TOKEN", "")


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"ok": True, "service": "stable_local_pending_server"})
            return
        self._send_json(404, {"ok": False, "reason": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/stable/pending":
            self._send_json(404, {"ok": False, "reason": "not_found"})
            return
        if TOKEN and self.headers.get("X-Stable-Pending-Token", "") != TOKEN:
            self._send_json(401, {"ok": False, "reason": "unauthorized"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "reason": "invalid_json"})
            return

        ticker = str(payload.get("ticker", "")).strip()
        signal_date = str(payload.get("signal_date", "")).strip()
        if not ticker or not signal_date:
            self._send_json(400, {"ok": False, "reason": "missing_ticker_or_signal_date"})
            return

        result = add_pending_order(
            ticker,
            signal_date,
            score=str(payload.get("stable_score") or payload.get("score") or payload.get("tgs_score") or "120"),
            daily_rsi=str(payload.get("daily_rsi", "")),
            volume_ratio=str(payload.get("volume_ratio", "")),
        )
        self._send_json(200, result)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Stable local pending server listening on http://{HOST}:{PORT}")
    print("Paper trading only. This server only appends pending orders.")
    server.serve_forever()


if __name__ == "__main__":
    main()
