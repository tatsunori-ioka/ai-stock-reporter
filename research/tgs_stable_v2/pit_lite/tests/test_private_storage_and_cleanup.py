from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from pit_lite.cleanup import MARKER, cleanup_private_run
from pit_lite.safety import (
    SafetyError,
    assert_private_path,
    create_private_run,
    validate_private_tree,
)


RUN_ID = "synthetic-run-001"
STANDALONE_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "cleanup_private_data.py"
)


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def setup_synthetic_private_run(
    root: Path,
    *,
    payloads: dict[str, bytes] | None = None,
) -> tuple[Path, Path]:
    payloads = payloads or {
        "raw/synthetic.json": b'{"synthetic":"not licensed data"}'
    }
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    marker = root / MARKER
    marker.write_text("TGS_STABLE_V2_JQUANTS_PIT_LITE\n", encoding="utf-8")
    marker.chmod(0o600)
    run = root / "runs" / RUN_ID
    (root / "manifests").mkdir(mode=0o700)
    entries = []
    for relative, content in payloads.items():
        payload = run / relative
        payload.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload.write_bytes(content)
        payload.chmod(0o600)
        entries.append(
            {
                "relative_path": relative,
                "category": "raw_responses",
                "bytes": payload.stat().st_size,
                "sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
                "licensed_or_reconstructible": True,
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
        "run_id": RUN_ID,
        "private_root_marker": MARKER,
        "run_relative_path": f"runs/{RUN_ID}",
        "cleanup_status": "NOT_EXECUTED",
        "entries": entries,
    }
    manifest_path = root / "manifests" / f"{RUN_ID}.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_path.chmod(0o600)
    return run, manifest_path


def test_create_private_run_enforces_modes_and_required_categories(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private"
    run = create_private_run(RUN_ID, root=root)
    assert run == root / "runs" / RUN_ID
    assert mode(root) == 0o700
    assert mode(root / MARKER) == 0o600
    for relative in (
        "raw",
        "normalized",
        "normalized/request_cache",
        "normalized/bars",
        "normalized/masters",
        "universe_membership",
        "trade_ledger",
        "checkpoint",
    ):
        assert (run / relative).is_dir()
        assert mode(run / relative) == 0o700
    assert validate_private_tree(root) == root.resolve()


def test_validate_private_tree_rejects_world_readable_private_file(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private"
    run = create_private_run(RUN_ID, root=root)
    unsafe = run / "raw" / "unsafe.json"
    unsafe.write_text("{}", encoding="utf-8")
    unsafe.chmod(0o644)
    with pytest.raises(SafetyError, match="0600"):
        validate_private_tree(root)


def test_private_path_rejects_escape_and_symlink(tmp_path: Path) -> None:
    root = tmp_path / "private"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(SafetyError, match="escapes"):
        assert_private_path(outside, root=root)
    link = root / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(SafetyError, match="symbolic"):
        assert_private_path(link, root=root)


def test_cleanup_defaults_to_verified_dry_run_and_preserves_all_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private"
    run, manifest_path = setup_synthetic_private_run(root)
    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    result = cleanup_private_run(
        RUN_ID,
        root=root,
        allow_test_root=True,
    )
    after = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert result["status"] == "DRY_RUN_VERIFIED"
    assert result["execute"] is False
    assert result["verified_file_count"] == 1
    assert run.is_dir()
    assert manifest_path.is_file()
    assert after == before


def test_cleanup_script_copy_runs_standalone_dry_run_without_repository_imports(
    tmp_path: Path,
) -> None:
    root = tmp_path / "standalone-private-root"
    run, _ = setup_synthetic_private_run(root)
    copied_script = root / "cleanup_private_data.py"
    shutil.copy2(STANDALONE_SCRIPT, copied_script)
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(tmp_path / "definitely-no-repository-imports"),
        "PYTHONNOUSERSITE": "1",
    }
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            str(copied_script),
            "--run-id",
            RUN_ID,
        ],
        cwd=root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "DRY_RUN_VERIFIED"
    assert result["execute"] is False
    assert (run / "raw" / "synthetic.json").is_file()


def test_cleanup_fails_closed_if_manifest_does_not_exactly_cover_run(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private"
    run, _ = setup_synthetic_private_run(root)
    extra = run / "checkpoint" / "extra.json"
    extra.parent.mkdir(mode=0o700)
    extra.write_text("{}", encoding="utf-8")
    extra.chmod(0o600)
    with pytest.raises(SafetyError, match="exactly cover"):
        cleanup_private_run(RUN_ID, root=root, allow_test_root=True)


def test_cleanup_fails_closed_on_hash_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "private"
    run, _ = setup_synthetic_private_run(root)
    (run / "raw" / "synthetic.json").write_bytes(b"tampered")
    with pytest.raises(SafetyError, match="size or hash"):
        cleanup_private_run(RUN_ID, root=root, allow_test_root=True)


@pytest.mark.parametrize(
    ("confirmation", "reason"),
    [
        ("wrong-run-id", "premium_to_standard"),
        (RUN_ID, None),
        (RUN_ID, "unapproved_reason"),
    ],
)
def test_cleanup_execution_requires_exact_confirmation_and_approved_reason(
    tmp_path: Path,
    confirmation: str,
    reason: str | None,
) -> None:
    root = tmp_path / "private"
    run, _ = setup_synthetic_private_run(root)
    with pytest.raises(SafetyError):
        cleanup_private_run(
            RUN_ID,
            root=root,
            execute=True,
            confirm_run_id=confirmation,
            reason=reason,
            allow_test_root=True,
        )
    assert run.is_dir()
    assert (run / "raw" / "synthetic.json").is_file()


def test_cleanup_execution_deletes_only_manifest_verified_synthetic_run(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private"
    run, manifest_path = setup_synthetic_private_run(root)
    unrelated = root / "runs" / "unrelated-run"
    unrelated.mkdir(mode=0o700)
    unrelated_payload = unrelated / "keep.txt"
    unrelated_payload.write_text("keep", encoding="utf-8")
    unrelated_payload.chmod(0o600)
    result = cleanup_private_run(
        RUN_ID,
        root=root,
        execute=True,
        confirm_run_id=RUN_ID,
        reason="paid_period_end",
        allow_test_root=True,
    )
    assert result["status"] == "COMPLETE"
    assert not run.exists()
    assert unrelated_payload.read_text(encoding="utf-8") == "keep"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["cleanup_status"] == "COMPLETE"
    assert manifest["remaining_file_count"] == 0
    assert manifest["entries"] == []
    receipt = json.loads(
        (root / "receipts" / f"{RUN_ID}.json").read_text(encoding="utf-8")
    )
    assert receipt["status"] == "COMPLETE"
    assert receipt["remaining_file_count"] == 0


def test_standalone_cleanup_partial_failure_rewrites_manifest_for_retry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "private"
    run, manifest_path = setup_synthetic_private_run(
        root,
        payloads={
            "raw/deletes-first.json": b"delete me",
            "normalized/remains-once.json": b"retry me",
        },
    )
    spec = importlib.util.spec_from_file_location(
        "standalone_cleanup_partial_failure_test",
        STANDALONE_SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    cleanup_script = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = cleanup_script
    spec.loader.exec_module(cleanup_script)
    monkeypatch.setattr(cleanup_script, "CONTRACTED_PRIVATE_ROOT", root)

    failed_target = (run / "normalized" / "remains-once.json").resolve()
    original_unlink = Path.unlink
    failed = False

    def fail_target_once(path: Path, *args, **kwargs) -> None:
        nonlocal failed
        if path.resolve() == failed_target and not failed:
            failed = True
            raise PermissionError("synthetic one-shot deletion failure")
        original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as deletion_patch:
        deletion_patch.setattr(Path, "unlink", fail_target_once)
        first = cleanup_script.cleanup_private_run(
            RUN_ID,
            execute=True,
            confirm_run_id=RUN_ID,
            reason="paid_period_end",
        )

    assert first["status"] == "PARTIAL_FAILURE"
    assert first["remaining_file_count"] == 1
    assert not (run / "raw" / "deletes-first.json").exists()
    assert failed_target.is_file()
    narrowed = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert narrowed["cleanup_status"] == "PARTIAL_FAILURE"
    assert narrowed["remaining_file_count"] == 1
    assert [entry["relative_path"] for entry in narrowed["entries"]] == [
        "normalized/remains-once.json"
    ]

    second = cleanup_script.cleanup_private_run(
        RUN_ID,
        execute=True,
        confirm_run_id=RUN_ID,
        reason="paid_period_end",
    )
    assert second["status"] == "COMPLETE"
    assert second["verified_file_count"] == 1
    assert second["remaining_file_count"] == 0
    assert not run.exists()
    completed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert completed_manifest["cleanup_status"] == "COMPLETE"
    assert completed_manifest["remaining_file_count"] == 0
    assert completed_manifest["entries"] == []
