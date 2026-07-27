from __future__ import annotations

from pathlib import Path
from typing import Any

from .contract import PRIVATE_ROOT, sha256_file
from .safety import atomic_write_json, assert_private_path


def _category(relative: Path) -> str:
    first = relative.parts[0] if relative.parts else ""
    return {
        "raw": "raw_responses",
        "normalized": "normalized_or_reconstructible_data",
        "universe_membership": "annual_membership",
        "trade_ledger": "exact_trade_ledger",
        "checkpoint": "checkpoint_and_attempt_journal",
    }.get(first, "private_run_metadata")


def build_deletion_manifest(run_id: str, run_directory: Path) -> dict[str, Any]:
    root = PRIVATE_ROOT.expanduser().resolve()
    run = assert_private_path(run_directory)
    entries: list[dict[str, Any]] = []
    for path in sorted(item for item in run.rglob("*") if item.is_file()):
        relative = path.relative_to(run)
        category = _category(relative)
        entries.append(
            {
                "relative_path": relative.as_posix(),
                "category": category,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "licensed_or_reconstructible": category
                not in {"private_run_metadata"},
                "minimum_plan": "Premium",
                "deletion_triggers": [
                    "premium_to_standard",
                    "paid_period_end",
                    "membership_withdrawal",
                ],
            }
        )
    manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "private_root_marker": ".tgs_stable_v2_private_root",
        "run_relative_path": str(run.relative_to(root)),
        "cleanup_status": "NOT_EXECUTED",
        "entries": entries,
    }
    target = root / "manifests" / f"{run_id}.json"
    atomic_write_json(target, manifest)
    return manifest
