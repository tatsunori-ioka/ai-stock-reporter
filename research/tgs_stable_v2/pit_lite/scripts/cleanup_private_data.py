#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


MARKER = ".tgs_stable_v2_private_root"
ALLOWED_REASONS = {
    "premium_to_standard",
    "paid_period_end",
    "membership_withdrawal",
}
CONTRACTED_PRIVATE_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "TGSStableV2"
    / "JQuantsPITLite"
)


class SafetyError(RuntimeError):
    """Fail-closed cleanup validation error."""


def _default_root() -> Path:
    script_directory = Path(__file__).resolve().parent
    if (script_directory / MARKER).is_file():
        return script_directory
    return CONTRACTED_PRIVATE_ROOT


def _safe_run_id(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{7,79}", value))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        payload = (
            json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        with os.fdopen(descriptor, "wb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def cleanup_private_run(
    run_id: str,
    *,
    execute: bool = False,
    confirm_run_id: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    if not _safe_run_id(run_id):
        raise SafetyError("unsafe run_id")
    root = _default_root().expanduser().resolve()
    if root.is_symlink() or not (root / MARKER).is_file():
        raise SafetyError("private root marker is absent or unsafe")
    run = root / "runs" / run_id
    if run.is_symlink() or not run.is_dir() or run.resolve().parent != (root / "runs").resolve():
        raise SafetyError("run directory is absent or unsafe")
    manifest_path = root / "manifests" / f"{run_id}.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise SafetyError("deletion manifest is absent or unsafe")
    manifest = _read_json(manifest_path)
    if manifest.get("run_id") != run_id:
        raise SafetyError("manifest run_id mismatch")

    expected: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("entries", []):
        relative = Path(str(entry["relative_path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise SafetyError("manifest contains an unsafe path")
        path = run / relative
        resolved_path = path.resolve()
        if resolved_path.parent != run.resolve() and run.resolve() not in resolved_path.parents:
            raise SafetyError("manifest path escapes the run directory")
        expected[relative.as_posix()] = entry
    actual = {
        path.relative_to(run).as_posix(): path
        for path in run.rglob("*")
        if path.is_file()
    }
    if set(actual) != set(expected):
        raise SafetyError("manifest does not exactly cover private run files")
    for relative, path in actual.items():
        if path.is_symlink():
            raise SafetyError("symbolic links are forbidden")
        entry = expected[relative]
        if (
            path.stat().st_size != int(entry["bytes"])
            or _sha256_file(path) != entry["sha256"]
        ):
            raise SafetyError("manifest size or hash verification failed")

    summary = {
        "run_id": run_id,
        "execute": execute,
        "verified_file_count": len(actual),
        "verified_bytes": sum(path.stat().st_size for path in actual.values()),
        "status": "DRY_RUN_VERIFIED" if not execute else "PENDING",
    }
    if not execute:
        return summary
    if confirm_run_id != run_id:
        raise SafetyError("execute requires an exact repeated run_id")
    if reason not in ALLOWED_REASONS:
        raise SafetyError("execute requires an approved deletion reason")

    failures: list[str] = []
    for relative in sorted(
        actual,
        key=lambda value: (value.count("/"), value),
        reverse=True,
    ):
        try:
            actual[relative].unlink()
        except OSError:
            failures.append(relative)
    for directory in sorted(
        (path for path in run.rglob("*") if path.is_dir()),
        key=lambda value: len(value.parts),
        reverse=True,
    ):
        try:
            directory.rmdir()
        except OSError:
            pass
    try:
        run.rmdir()
    except OSError:
        pass

    remaining = [relative for relative, path in actual.items() if path.exists()]
    status = (
        "COMPLETE"
        if not failures and not remaining and not run.exists()
        else "PARTIAL_FAILURE"
    )
    manifest["cleanup_status"] = status
    manifest["cleanup_reason"] = reason
    manifest["remaining_file_count"] = len(remaining)
    if status == "PARTIAL_FAILURE":
        manifest["entries"] = [expected[relative] for relative in sorted(remaining)]
    else:
        manifest["entries"] = []
    _atomic_write_json(manifest_path, manifest)
    receipt = {
        "run_id": run_id,
        "reason": reason,
        "status": status,
        "verified_file_count": len(actual),
        "remaining_file_count": len(remaining),
    }
    _atomic_write_json(root / "receipts" / f"{run_id}.json", receipt)
    summary.update(receipt)
    return summary


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Manifest-verified J-Quants private-data cleanup (dry-run by default)."
    )
    value.add_argument("--run-id", required=True)
    value.add_argument("--execute", action="store_true")
    value.add_argument("--confirm-run-id")
    value.add_argument(
        "--reason",
        choices=["premium_to_standard", "paid_period_end", "membership_withdrawal"],
    )
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        result = cleanup_private_run(
            args.run_id,
            execute=args.execute,
            confirm_run_id=args.confirm_run_id,
            reason=args.reason,
        )
    except SafetyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
