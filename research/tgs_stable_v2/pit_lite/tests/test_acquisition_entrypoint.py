from __future__ import annotations

import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "acquire_jquants_pit_lite.py"
SPEC = importlib.util.spec_from_file_location("acquire_jquants_pit_lite_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
acquire_script = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = acquire_script
SPEC.loader.exec_module(acquire_script)


def test_estimate_is_zero_network_zero_environment_zero_write() -> None:
    estimate = acquire_script.estimate()
    assert estimate["network_requests"] == 0
    assert estimate["environment_read"] is False
    assert estimate["filesystem_writes"] == 0
    assert estimate["absolute_hard_attempt_limit"] == 3000
    assert estimate["primary"]["expected_attempts"] < 3000
    assert estimate["primary"]["planned_worst_case_attempts"] < 3000
    assert estimate["deterministic_fallback"]["planned_worst_case_attempts"] == 2373


def test_live_checks_filevault_before_hashes_environment_writes_or_network(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        acquire_script,
        "parser",
        lambda: SimpleNamespace(
            parse_args=lambda: SimpleNamespace(
                estimate=False,
                live=True,
                run_id="synthetic-run-001",
                resume=False,
                prior_attempts=0,
            )
        ),
    )
    monkeypatch.setattr(acquire_script, "filevault_is_active", lambda: False)
    monkeypatch.setattr(
        acquire_script,
        "verify_protected_inputs",
        lambda: (_ for _ in ()).throw(AssertionError("hash gate reached")),
    )
    monkeypatch.setattr(
        acquire_script,
        "verify_production_files",
        lambda: (_ for _ in ()).throw(AssertionError("production gate reached")),
    )
    monkeypatch.setattr(
        acquire_script,
        "create_private_run",
        lambda _: (_ for _ in ()).throw(AssertionError("private write reached")),
    )
    result = acquire_script.main()
    assert result == 3
    assert "FileVault preflight did not return active" in capsys.readouterr().err


def test_missing_key_stops_before_private_write_or_network(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        acquire_script,
        "parser",
        lambda: SimpleNamespace(
            parse_args=lambda: SimpleNamespace(
                estimate=False,
                live=True,
                run_id="synthetic-run-001",
                resume=False,
                prior_attempts=0,
            )
        ),
    )
    monkeypatch.setattr(acquire_script, "filevault_is_active", lambda: True)
    monkeypatch.setattr(acquire_script, "verify_protected_inputs", lambda: {})
    monkeypatch.setattr(acquire_script, "verify_production_files", lambda: {})
    monkeypatch.setattr(acquire_script.os, "environ", {})
    monkeypatch.setattr(
        acquire_script,
        "create_private_run",
        lambda _: (_ for _ in ()).throw(AssertionError("private write reached")),
    )
    monkeypatch.setattr(
        acquire_script,
        "SafeApiClient",
        lambda *_: (_ for _ in ()).throw(AssertionError("network client reached")),
    )
    result = acquire_script.main()
    captured = capsys.readouterr()
    assert result == 4
    assert "JQUANTS_API_KEY is unset" in captured.err
    assert "x-api-key" not in captured.err


def test_private_acquisition_lock_rejects_second_concurrent_holder(
    tmp_path: Path,
    monkeypatch,
) -> None:
    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    monkeypatch.setattr(acquire_script, "PRIVATE_ROOT", private_root)
    with acquire_script.private_acquisition_lock():
        with pytest.raises(
            acquire_script.SafetyError,
            match="another private J-Quants acquisition is already active",
        ):
            with acquire_script.private_acquisition_lock():
                raise AssertionError("second lock unexpectedly acquired")
    # The first context released the advisory lock.
    with acquire_script.private_acquisition_lock():
        pass


def test_concurrent_lock_failure_does_not_rebuild_active_run_manifest(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    private_root = tmp_path / "private"
    run = private_root / "runs" / "active-run-001"
    run.mkdir(parents=True)
    manifest = private_root / "manifests" / "active-run-001.json"
    manifest.parent.mkdir()
    sentinel = '{"active_writer_owns_this":true}\n'
    manifest.write_text(sentinel, encoding="utf-8")
    monkeypatch.setattr(
        acquire_script,
        "parser",
        lambda: SimpleNamespace(
            parse_args=lambda: SimpleNamespace(
                estimate=False,
                live=True,
                run_id="active-run-001",
                resume=True,
                prior_attempts=0,
            )
        ),
    )
    monkeypatch.setattr(acquire_script, "PRIVATE_ROOT", private_root)
    monkeypatch.setattr(acquire_script, "filevault_is_active", lambda: True)
    monkeypatch.setattr(acquire_script, "verify_protected_inputs", lambda: {})
    monkeypatch.setattr(acquire_script, "verify_production_files", lambda: {})
    monkeypatch.setattr(
        acquire_script.os,
        "environ",
        {acquire_script.API_KEY_ENV: "synthetic-not-a-real-key"},
    )
    monkeypatch.setattr(acquire_script, "create_private_run", lambda _run_id: run)

    @contextmanager
    def reject_lock():
        raise acquire_script.SafetyError(
            "another private J-Quants acquisition is already active"
        )
        yield

    manifest_calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(acquire_script, "private_acquisition_lock", reject_lock)
    monkeypatch.setattr(
        acquire_script,
        "build_deletion_manifest",
        lambda *args, **_kwargs: manifest_calls.append(args),
    )
    monkeypatch.setattr(
        acquire_script,
        "install_private_cleanup_script",
        lambda: (_ for _ in ()).throw(
            AssertionError("cleanup install ran without acquisition lock")
        ),
    )

    result = acquire_script.main()
    assert result == 6
    assert manifest_calls == []
    assert manifest.read_text(encoding="utf-8") == sentinel
    assert "another private J-Quants acquisition is already active" in (
        capsys.readouterr().err
    )
