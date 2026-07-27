from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .contract import PRIVATE_ROOT, sha256_file
from .safety import SafetyError, atomic_write_json, read_json


ALLOWED_REASONS = {
    "premium_to_standard",
    "paid_period_end",
    "membership_withdrawal",
}
MARKER = ".tgs_stable_v2_private_root"


def _safe_run_id(value: str) -> bool:
    return (
        8 <= len(value) <= 80
        and value[0].isalnum()
        and all(character.islower() or character.isdigit() or character in "._-" for character in value)
    )


def cleanup_private_run(
    run_id: str,
    *,
    root: Path = PRIVATE_ROOT,
    execute: bool = False,
    confirm_run_id: str | None = None,
    reason: str | None = None,
    allow_test_root: bool = False,
) -> dict[str, Any]:
    if not _safe_run_id(run_id):
        raise SafetyError("unsafe run_id")
    resolved_root = root.expanduser().resolve()
    if not allow_test_root and resolved_root != PRIVATE_ROOT.expanduser().resolve():
        raise SafetyError("cleanup root differs from the contracted private root")
    if resolved_root.is_symlink() or not (resolved_root / MARKER).is_file():
        raise SafetyError("private root marker is absent or unsafe")
    run = resolved_root / "runs" / run_id
    if run.is_symlink() or not run.is_dir() or run.resolve().parent != (resolved_root / "runs").resolve():
        raise SafetyError("run directory is absent or unsafe")
    manifest_path = resolved_root / "manifests" / f"{run_id}.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise SafetyError("deletion manifest is absent or unsafe")
    manifest = read_json(manifest_path)
    if manifest.get("run_id") != run_id:
        raise SafetyError("manifest run_id mismatch")

    expected: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("entries", []):
        relative = Path(str(entry["relative_path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise SafetyError("manifest contains an unsafe path")
        path = run / relative
        if path.resolve().parent != run.resolve() and run.resolve() not in path.resolve().parents:
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
        if path.stat().st_size != int(entry["bytes"]) or sha256_file(path) != entry["sha256"]:
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
    for relative in sorted(actual, key=lambda value: (value.count("/"), value), reverse=True):
        path = actual[relative]
        try:
            path.unlink()
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
    status = "COMPLETE" if not failures and not remaining and not run.exists() else "PARTIAL_FAILURE"
    manifest["cleanup_status"] = status
    manifest["cleanup_reason"] = reason
    manifest["remaining_file_count"] = len(remaining)
    if status == "PARTIAL_FAILURE":
        # Keep a retryable, exact manifest for only the files that remain.
        manifest["entries"] = [expected[relative] for relative in sorted(remaining)]
    else:
        # Do not retain security-code-bearing private paths after deletion.
        manifest["entries"] = []
    atomic_write_json(manifest_path, manifest)
    receipt = {
        "run_id": run_id,
        "reason": reason,
        "status": status,
        "verified_file_count": len(actual),
        "remaining_file_count": len(remaining),
    }
    atomic_write_json(resolved_root / "receipts" / f"{run_id}.json", receipt)
    summary.update(receipt)
    return summary
