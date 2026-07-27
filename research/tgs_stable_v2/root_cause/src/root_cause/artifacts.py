from __future__ import annotations

import csv
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from pit_lite.safety import SafetyError, assert_aggregate_mapping

from .contract import CONTRACT, REPORT_PATH, RESULTS_ROOT, canonical_sha256
from .contract import ROOT_CAUSE_ROOT


PROVENANCE = {
    "gate_id": CONTRACT["gate_id"],
    "model_id": CONTRACT["model_id"],
    "base_commit": CONTRACT["base_commit"],
    "classification": CONTRACT["classification"],
    "source_run_id": CONTRACT["source_run_id"],
}
ALLOWED_RESULTS = set(CONTRACT["repository_output_policy"]["allowed_results"])
FORBIDDEN_COLUMNS = {
    "code",
    "ticker",
    "security_id",
    "symbol",
    "company",
    "name",
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
}
CREDENTIAL_PATTERNS = (
    re.compile(
        r"(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret)"
        r"\s*[:=]\s*[\"'][A-Za-z0-9._+/=-]{16,}[\"']"
    ),
    re.compile(r"(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
)


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, Mapping):
        return {str(key): _plain(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [_plain(child) for child in value]
    raise SafetyError(f"unsupported aggregate artifact value: {type(value).__name__}")


def validate_json_document(value: Mapping[str, Any]) -> dict[str, Any]:
    document = _plain(dict(value))
    assert isinstance(document, dict)
    assert_aggregate_mapping(document)
    json.dumps(document, ensure_ascii=False, allow_nan=False)
    return document


def validate_csv_records(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    materialized = [_plain(dict(row)) for row in rows]
    if not materialized:
        raise SafetyError("aggregate CSV must contain at least one record")
    columns = list(materialized[0])
    for row in materialized:
        if list(row) != columns:
            raise SafetyError("aggregate CSV records must have identical columns")
        assert_aggregate_mapping(row)
    return materialized


def with_provenance(row: Mapping[str, Any]) -> dict[str, Any]:
    return {**PROVENANCE, **dict(row)}


def artifact_bundle_sha256(
    csv_documents: Mapping[str, list[Mapping[str, Any]]],
    json_documents: Mapping[str, Mapping[str, Any]],
    report: str,
) -> str:
    payload = {
        "csv": {
            name: validate_csv_records(records)
            for name, records in sorted(csv_documents.items())
        },
        "json": {
            name: validate_json_document(document)
            for name, document in sorted(json_documents.items())
        },
        "report": report,
    }
    return canonical_sha256(payload)


def write_artifacts(
    csv_documents: Mapping[str, list[Mapping[str, Any]]],
    json_documents: Mapping[str, Mapping[str, Any]],
    report: str,
    *,
    results_root: Path = RESULTS_ROOT,
    report_path: Path = REPORT_PATH,
) -> str:
    filenames = set(csv_documents) | set(json_documents)
    if filenames != ALLOWED_RESULTS:
        raise SafetyError(
            "result allowlist mismatch: "
            f"expected {sorted(ALLOWED_RESULTS)}, got {sorted(filenames)}"
        )
    if not report.strip():
        raise SafetyError("diagnostic report is empty")
    if "JQUANTS_API_KEY" in report or "Authorization:" in report:
        raise SafetyError("report contains credential-shaped content")

    results_root.mkdir(parents=True, exist_ok=True)
    for name, rows in sorted(csv_documents.items()):
        if name not in ALLOWED_RESULTS or not name.endswith(".csv"):
            raise SafetyError(f"unsafe CSV artifact name: {name}")
        records = validate_csv_records(rows)
        path = results_root / name
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(
                target,
                fieldnames=list(records[0]),
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(records)

    for name, document in sorted(json_documents.items()):
        if name not in ALLOWED_RESULTS or not name.endswith(".json"):
            raise SafetyError(f"unsafe JSON artifact name: {name}")
        validated = validate_json_document(document)
        (results_root / name).write_text(
            json.dumps(
                validated,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.rstrip() + "\n", encoding="utf-8")
    return artifact_bundle_sha256(csv_documents, json_documents, report)


def scan_repository_outputs(
    *,
    results_root: Path = RESULTS_ROOT,
    report_path: Path = REPORT_PATH,
) -> dict[str, int]:
    licensed_raw_findings = 0
    credential_findings = 0
    actual_files = {
        path.name for path in results_root.iterdir() if path.is_file()
    }
    if actual_files != ALLOWED_RESULTS:
        licensed_raw_findings += len(actual_files ^ ALLOWED_RESULTS)
    for path in sorted(results_root.iterdir()):
        if not path.is_file():
            continue
        if path.suffix == ".json":
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                validate_json_document(value)
            except (ValueError, TypeError, SafetyError):
                licensed_raw_findings += 1
        elif path.suffix == ".csv":
            try:
                with path.open(encoding="utf-8", newline="") as source:
                    reader = csv.DictReader(source)
                    if reader.fieldnames is None:
                        raise SafetyError("CSV header missing")
                    normalized = {
                        field.strip().lower() for field in reader.fieldnames
                    }
                    if normalized & FORBIDDEN_COLUMNS or any(
                        field.startswith("adj") for field in normalized
                    ):
                        raise SafetyError("identifier or market-data column found")
                    validate_csv_records(list(reader))
            except (ValueError, TypeError, SafetyError):
                licensed_raw_findings += 1
        else:
            licensed_raw_findings += 1
    if not report_path.is_file() or not report_path.read_text(
        encoding="utf-8"
    ).strip():
        licensed_raw_findings += 1

    for path in sorted(ROOT_CAUSE_ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in {
            ".py",
            ".json",
            ".csv",
            ".md",
        }:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        credential_findings += sum(
            len(pattern.findall(text)) for pattern in CREDENTIAL_PATTERNS
        )
    return {
        "licensed_raw_findings": licensed_raw_findings,
        "credential_findings": credential_findings,
    }
