from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


PIT_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = PIT_ROOT.parent
REPOSITORY_ROOT = V2_ROOT.parents[1]
CONTRACT_PATH = PIT_ROOT / "contracts" / "PIT_LITE_RESEARCH_CONTRACT.json"
RESULTS_ROOT = PIT_ROOT / "results"
REPORT_PATH = PIT_ROOT / "reports" / "PIT_LITE_U15_U50_U100_REPORT.md"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected an object in {path.name}")
    return value


CONTRACT = read_json(CONTRACT_PATH)
GATE_ID = str(CONTRACT["gate_id"])
MODEL_ID = str(CONTRACT["model_id"])
BASE_COMMIT = str(CONTRACT["base_commit"])
CLASSIFICATION = str(CONTRACT["classification"])
PRIVATE_ROOT = Path(str(CONTRACT["private_storage"]["root"]))


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


def verify_protected_inputs() -> dict[str, str]:
    actual: dict[str, str] = {}
    failures: list[str] = []
    for relative, expected in CONTRACT["protected_inputs_sha256"].items():
        path = REPOSITORY_ROOT / relative
        if not path.is_file():
            failures.append(f"{relative}: missing")
            continue
        digest = sha256_file(path)
        actual[relative] = digest
        if digest != expected:
            failures.append(f"{relative}: hash mismatch")
    if failures:
        raise RuntimeError("protected input verification failed: " + "; ".join(failures))
    return actual


def verify_production_files() -> dict[str, str]:
    actual: dict[str, str] = {}
    failures: list[str] = []
    for relative, expected in CONTRACT["production_sha256"].items():
        path = REPOSITORY_ROOT / relative
        if not path.is_file():
            failures.append(f"{relative}: missing")
            continue
        digest = sha256_file(path)
        actual[relative] = digest
        if digest != expected:
            failures.append(f"{relative}: hash mismatch")
    if failures:
        raise RuntimeError("production freeze verification failed: " + "; ".join(failures))
    return actual
