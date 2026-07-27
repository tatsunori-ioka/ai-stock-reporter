#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from typing import Any


ROOT_CAUSE_ROOT = Path(__file__).resolve().parents[1]
V2_ROOT = ROOT_CAUSE_ROOT.parent
REPOSITORY_ROOT = V2_ROOT.parents[1]
for source in (
    ROOT_CAUSE_ROOT / "src",
    V2_ROOT / "pit_lite" / "src",
    V2_ROOT / "src",
    REPOSITORY_ROOT,
):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))


def _blocked(*args: Any, **kwargs: Any) -> Any:
    del args, kwargs
    raise RuntimeError("diagnostic network access is blocked")


def _install_network_guard() -> None:
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked
    original_socket = socket.socket

    class OfflineSocket(original_socket):
        def connect(self, *args: Any, **kwargs: Any) -> Any:
            return _blocked(*args, **kwargs)

        def connect_ex(self, *args: Any, **kwargs: Any) -> Any:
            return _blocked(*args, **kwargs)

    socket.socket = OfflineSocket


def _assert_no_provider_imports() -> None:
    banned = (
        "requests",
        "httpx",
        "urllib.request",
        "http.client",
        "urllib3",
        "pit_lite.api",
        "pit_lite.acquisition",
    )
    source_root = ROOT_CAUSE_ROOT / "src"
    script_root = ROOT_CAUSE_ROOT / "scripts"
    for path in sorted([*source_root.rglob("*.py"), *script_root.rglob("*.py")]):
        if path == Path(__file__):
            continue
        text = path.read_text(encoding="utf-8")
        for module in banned:
            if f"import {module}" in text or f"from {module} import" in text:
                raise RuntimeError(f"banned provider/network import in {path.name}")


def main() -> int:
    if "JQUANTS_API_KEY" in os.environ:
        print(
            "error: remove JQUANTS_API_KEY from the diagnostic environment",
            file=sys.stderr,
        )
        return 2
    _install_network_guard()
    _assert_no_provider_imports()
    from root_cause.pipeline import run_root_cause_diagnostic

    try:
        result = run_root_cause_diagnostic()
    except (RuntimeError, ValueError) as exc:
        print(
            f"error: {type(exc).__name__}: diagnostic stopped",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
