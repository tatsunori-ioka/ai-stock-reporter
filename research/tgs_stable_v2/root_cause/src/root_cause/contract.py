from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any, Iterable

from pit_lite.safety import validate_private_tree


ROOT_CAUSE_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = ROOT_CAUSE_ROOT.parent
REPOSITORY_ROOT = V2_ROOT.parents[1]
PIT_ROOT = V2_ROOT / "pit_lite"
CONTRACT_PATH = (
    ROOT_CAUSE_ROOT / "contracts" / "ROOT_CAUSE_DIAGNOSTIC_CONTRACT.json"
)
RESULTS_ROOT = ROOT_CAUSE_ROOT / "results"
REPORT_PATH = ROOT_CAUSE_ROOT / "reports" / "ROOT_CAUSE_DIAGNOSTIC_REPORT.md"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


CONTRACT: dict[str, Any] = read_json(CONTRACT_PATH)
GATE_ID = str(CONTRACT["gate_id"])
MODEL_ID = str(CONTRACT["model_id"])
BASE_COMMIT = str(CONTRACT["base_commit"])
CLASSIFICATION = str(CONTRACT["classification"])
SOURCE_RUN_ID = str(CONTRACT["source_run_id"])
PRIVATE_ROOT = Path(str(CONTRACT["private_input"]["root"]))
RUN_DIRECTORY = PRIVATE_ROOT / str(CONTRACT["private_input"]["run_relative_path"])
MANIFEST_PATH = PRIVATE_ROOT / str(
    CONTRACT["private_input"]["manifest_relative_path"]
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_hash_map(mapping: dict[str, str], label: str) -> dict[str, str]:
    actual: dict[str, str] = {}
    failures: list[str] = []
    for relative, expected in mapping.items():
        path = REPOSITORY_ROOT / relative
        if not path.is_file() or path.is_symlink():
            failures.append(f"{relative}: missing or unsafe")
            continue
        digest = sha256_file(path)
        actual[relative] = digest
        if digest != expected:
            failures.append(f"{relative}: hash mismatch")
    if failures:
        raise RuntimeError(f"{label} verification failed: " + "; ".join(failures))
    return actual


def verify_upstream_research() -> dict[str, str]:
    return _verify_hash_map(
        dict(CONTRACT["upstream_research_sha256"]),
        "upstream research",
    )


def verify_pit_protected_inputs() -> dict[str, str]:
    return _verify_hash_map(
        dict(CONTRACT["pit_protected_inputs_sha256"]),
        "PIT protected input",
    )


def verify_production_files() -> dict[str, str]:
    return _verify_hash_map(
        dict(CONTRACT["production_sha256"]),
        "production",
    )


def filevault_is_active() -> bool:
    result = subprocess.run(
        ["/usr/bin/fdesetup", "status"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.returncode == 0 and "FileVault is On" in result.stdout


def _category_bundle(run: Path, category: str) -> tuple[str, int]:
    files = sorted(path for path in (run / category).rglob("*") if path.is_file())
    entries = [
        (str(path.relative_to(run)), sha256_file(path))
        for path in files
    ]
    return canonical_sha256(entries), len(files)


def _implementation_bundle_sha256() -> str:
    entries = [
        (str(path.relative_to(PIT_ROOT)), sha256_file(path))
        for path in sorted(
            [
                *PIT_ROOT.joinpath("src").rglob("*.py"),
                *PIT_ROOT.joinpath("scripts").rglob("*.py"),
                *PIT_ROOT.joinpath("tests").rglob("*.py"),
            ]
        )
    ]
    return canonical_sha256(entries)


def _safe_relative_paths(paths: Iterable[Path], root: Path) -> set[str]:
    result: set[str] = set()
    for path in paths:
        if path.is_symlink():
            raise RuntimeError("private input contains a symbolic link")
        result.add(path.relative_to(root).as_posix())
    return result


def verify_private_inputs() -> dict[str, Any]:
    if not filevault_is_active():
        raise RuntimeError("FileVault is not active")
    unresolved = (
        PRIVATE_ROOT.expanduser(),
        RUN_DIRECTORY.expanduser(),
        MANIFEST_PATH.expanduser(),
    )
    if any(path.is_symlink() for path in unresolved):
        raise RuntimeError("private root, run, and manifest must not be symlinks")
    root = unresolved[0].resolve()
    run = unresolved[1].resolve()
    manifest_path = unresolved[2].resolve()
    repository = REPOSITORY_ROOT.resolve()
    if run == repository or repository in run.parents:
        raise RuntimeError("private run must be outside the repository")
    if not root.is_dir() or not run.is_dir() or not manifest_path.is_file():
        raise RuntimeError("private root, run, or manifest is missing")
    validate_private_tree(root)
    if root.stat().st_uid != os.getuid():
        raise RuntimeError("private root owner mismatch")
    if sha256_file(manifest_path) != CONTRACT["private_input"]["manifest_sha256"]:
        raise RuntimeError("private manifest fingerprint mismatch")

    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise RuntimeError("private manifest is not an object")
    if manifest.get("run_id") != SOURCE_RUN_ID:
        raise RuntimeError("private manifest run_id mismatch")
    if manifest.get("cleanup_status") != "NOT_EXECUTED":
        raise RuntimeError("private cleanup status is not NOT_EXECUTED")
    rows = manifest.get("entries")
    if not isinstance(rows, list):
        raise RuntimeError("private manifest entries are missing")
    if len(rows) != int(CONTRACT["private_input"]["manifest_entry_count"]):
        raise RuntimeError("private manifest entry count mismatch")

    actual_files = sorted(path for path in run.rglob("*") if path.is_file())
    actual_relatives = _safe_relative_paths(actual_files, run)
    expected: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("private manifest contains a non-object entry")
        relative = str(row.get("relative_path", ""))
        path = (run / relative).resolve()
        if not relative or run not in path.parents:
            raise RuntimeError("private manifest contains an unsafe path")
        if relative in expected:
            raise RuntimeError("private manifest contains a duplicate path")
        expected[relative] = row
    if set(expected) != actual_relatives:
        raise RuntimeError("private manifest does not exactly cover the run")

    for relative, row in expected.items():
        path = run / relative
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("private manifest target is unsafe")
        if path.stat().st_size != int(row.get("bytes", -1)):
            raise RuntimeError("private file size mismatch")
        if sha256_file(path) != str(row.get("sha256", "")):
            raise RuntimeError("private file hash mismatch")
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise RuntimeError("private file mode is not 0600")
    directories = [root, run, *[path for path in run.rglob("*") if path.is_dir()]]
    if any(stat.S_IMODE(path.stat().st_mode) != 0o700 for path in directories):
        raise RuntimeError("private directory mode is not 0700")
    if stat.S_IMODE(manifest_path.stat().st_mode) != 0o600:
        raise RuntimeError("private manifest mode is not 0600")

    bundle_results: dict[str, dict[str, Any]] = {}
    for category, expected_hash in CONTRACT["private_input"][
        "category_bundle_sha256"
    ].items():
        digest, count = _category_bundle(run, str(category))
        if digest != expected_hash:
            raise RuntimeError(f"private {category} bundle fingerprint mismatch")
        bundle_results[str(category)] = {
            "sha256": digest,
            "file_count": count,
            "match": True,
        }

    source_fingerprints = read_json(
        PIT_ROOT / "results" / "data_fingerprints.json"
    )
    if source_fingerprints.get("run_id") != SOURCE_RUN_ID:
        raise RuntimeError("PR #10 source fingerprint run_id mismatch")
    if (
        source_fingerprints.get("contract_sha256")
        != CONTRACT["source_fingerprints"]["pit_lite_contract_sha256"]
        or source_fingerprints.get("implementation_bundle_sha256")
        != CONTRACT["source_fingerprints"]["pit_lite_implementation_bundle_sha256"]
    ):
        raise RuntimeError("PR #10 contract or implementation fingerprint mismatch")
    implementation_bundle = _implementation_bundle_sha256()
    if (
        implementation_bundle
        != CONTRACT["source_fingerprints"]["pit_lite_implementation_bundle_sha256"]
    ):
        raise RuntimeError("current PIT-lite implementation fingerprint mismatch")
    source_bundle_fields = {
        "normalized": "private_normalized_category_bundle_sha256",
        "universe_membership": "private_membership_category_bundle_sha256",
        "trade_ledger": "private_ledger_category_bundle_sha256",
    }
    for category, field in source_bundle_fields.items():
        if source_fingerprints.get(field) != bundle_results[category]["sha256"]:
            raise RuntimeError(f"PR #10 {category} fingerprint mismatch")

    upstream = verify_upstream_research()
    protected = verify_pit_protected_inputs()
    production = verify_production_files()
    return {
        "schema_version": "1.0",
        "gate_id": GATE_ID,
        "model_id": MODEL_ID,
        "base_commit": BASE_COMMIT,
        "classification": CLASSIFICATION,
        "source_run_id": SOURCE_RUN_ID,
        "manifest_sha256": sha256_file(manifest_path),
        "manifest_entry_count": len(rows),
        "manifest_exact_coverage": True,
        "manifest_hashes_and_sizes_match": True,
        "cleanup_status": manifest["cleanup_status"],
        "filevault_active": True,
        "private_owner_match": True,
        "private_directory_mode_0700": True,
        "private_file_mode_0600": True,
        "category_bundles": bundle_results,
        "pit_lite_implementation_bundle_sha256": implementation_bundle,
        "upstream_research_sha_match": (
            f"{len(upstream)}/{len(CONTRACT['upstream_research_sha256'])}"
        ),
        "protected_input_sha_match": (
            f"{len(protected)}/{len(CONTRACT['pit_protected_inputs_sha256'])}"
        ),
        "production_sha_match": (
            f"{len(production)}/{len(CONTRACT['production_sha256'])}"
        ),
        "network_calls": 0,
        "provider_api_calls": 0,
        "api_key_reads": 0,
        "private_writes": 0,
        "raw_licensed_data_committed": False,
    }
