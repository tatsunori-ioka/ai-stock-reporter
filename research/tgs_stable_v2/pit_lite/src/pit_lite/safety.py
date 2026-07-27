from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .contract import PRIVATE_ROOT, REPOSITORY_ROOT


class SafetyError(RuntimeError):
    """Fail-closed safety or privacy gate."""


def _within(path: Path, parent: Path) -> bool:
    resolved = path.resolve()
    root = parent.resolve()
    return resolved == root or root in resolved.parents


def assert_private_path(path: Path, *, root: Path = PRIVATE_ROOT) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise SafetyError("private path must not be a symbolic link")
    resolved = expanded.resolve()
    private_root = root.expanduser().resolve()
    if not _within(resolved, private_root):
        raise SafetyError("path escapes the approved private root")
    if _within(resolved, REPOSITORY_ROOT):
        raise SafetyError("licensed data path must be outside the repository")
    return resolved


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def validate_private_tree(root: Path = PRIVATE_ROOT) -> Path:
    resolved = assert_private_path(root, root=root)
    if not resolved.is_dir():
        raise SafetyError("private root does not exist")
    if _mode(resolved) != 0o700:
        raise SafetyError("private root mode must be 0700")
    if resolved.stat().st_uid != os.getuid():
        raise SafetyError("private root must be owned by the current user")
    for current, directories, files in os.walk(resolved, followlinks=False):
        current_path = Path(current)
        if current_path.is_symlink():
            raise SafetyError("symbolic links are forbidden in the private tree")
        if _mode(current_path) != 0o700:
            raise SafetyError("private directory mode must be 0700")
        for name in [*directories, *files]:
            child = current_path / name
            if child.is_symlink():
                raise SafetyError("symbolic links are forbidden in the private tree")
            if child.stat().st_uid != os.getuid():
                raise SafetyError("private tree item has an unexpected owner")
        for name in files:
            if _mode(current_path / name) != 0o600:
                raise SafetyError("private file mode must be 0600")
    return resolved


def create_private_run(run_id: str, *, root: Path = PRIVATE_ROOT) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{7,79}", run_id):
        raise SafetyError("run_id must be a safe 8-80 character lowercase identifier")
    resolved_root = root.expanduser().resolve()
    if _within(resolved_root, REPOSITORY_ROOT):
        raise SafetyError("private root must be outside the repository")
    old_umask = os.umask(0o077)
    try:
        resolved_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(resolved_root, 0o700)
        marker = resolved_root / ".tgs_stable_v2_private_root"
        if not marker.exists():
            atomic_write_text(marker, "TGS_STABLE_V2_JQUANTS_PIT_LITE\n")
        run = resolved_root / "runs" / run_id
        for path in (
            resolved_root / "runs",
            resolved_root / "manifests",
            resolved_root / "receipts",
            run,
            run / "raw",
            run / "normalized",
            run / "normalized" / "request_cache",
            run / "normalized" / "bars",
            run / "normalized" / "masters",
            run / "universe_membership",
            run / "trade_ledger",
            run / "checkpoint",
        ):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(path, 0o700)
    finally:
        os.umask(old_umask)
    validate_private_tree(resolved_root)
    return run


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_text(path: Path, value: str) -> None:
    atomic_write_bytes(path, value.encode("utf-8"))


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


FORBIDDEN_AGGREGATE_KEYS = {
    "ticker",
    "code",
    "name",
    "company",
    "security_id",
    "symbol",
    "trade_id",
    "signal_date",
    "entry_date",
    "exit_date",
    "entry_price",
    "exit_price",
    "entry_fill_price",
    "exit_fill_price",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "va",
    "rows",
    "data",
    "members",
    "constituents",
    "trades",
    "response_body",
    "raw_response",
}


def assert_aggregate_mapping(value: Any, *, location: str = "root") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_AGGREGATE_KEYS or normalized.startswith("adj"):
                raise SafetyError(f"forbidden aggregate key at {location}: {key}")
            assert_aggregate_mapping(child, location=f"{location}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            assert_aggregate_mapping(child, location=f"{location}[{index}]")


def redact_exception(exc: BaseException) -> SafetyError:
    return SafetyError(f"{type(exc).__name__}: operation failed; sensitive detail suppressed")
