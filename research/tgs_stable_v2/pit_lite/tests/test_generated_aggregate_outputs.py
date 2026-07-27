from __future__ import annotations

import csv
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from pit_lite.metrics import economic_gate
from pit_lite.safety import assert_aggregate_mapping


PIT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PIT_ROOT.parents[2]
RESULTS_ROOT = PIT_ROOT / "results"
REPORT_PATH = PIT_ROOT / "reports" / "PIT_LITE_U15_U50_U100_REPORT.md"
CONTRACT_PATH = PIT_ROOT / "contracts" / "PIT_LITE_RESEARCH_CONTRACT.json"

EXPECTED_RESULT_FILES = {
    "metrics_summary.json",
    "yearly_metrics.csv",
    "split_metrics.csv",
    "score_bucket_metrics.csv",
    "cost_sensitivity.csv",
    "concentration_metrics.csv",
    "universe_annual_counts.csv",
    "data_fingerprints.json",
    "request_audit_summary.json",
}
EXPECTED_ROW_COUNTS = {
    "universe_annual_counts.csv": 52,
    "yearly_metrics.csv": 52,
    "split_metrics.csv": 12,
    "score_bucket_metrics.csv": 16,
    "cost_sensitivity.csv": 12,
    "concentration_metrics.csv": 8,
}
LABEL_KEYS = (
    "run_id",
    "base_commit",
    "gate_id",
    "model_id",
    "classification",
)
EXPECTED_LABELS = {
    "run_id": "v2-r2a-20260727-d3b8ed0-integrity1",
    "base_commit": "d3b8ed0ec09d6d7fc70aeca5144f8bb6962c4073",
    "gate_id": "V2-R2A_PIT_LITE_UNIVERSE_COMPARISON",
    "model_id": "TGS_STABLE_V2_PIT_LITE",
    "classification": "PIT_LITE_EXPLORATORY_ONLY_NOT_FORMAL_CANDIDATE",
}
NONFINITE_TEXT = {"nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames
        rows = list(reader)
    assert all(None not in row for row in rows)
    return rows


def _assert_finite(value: Any, *, location: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            _assert_finite(child, location=f"{location}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _assert_finite(child, location=f"{location}[{index}]")
        return
    if isinstance(value, float):
        assert math.isfinite(value), location


def _assert_csv_cell_is_finite(value: str, *, location: str) -> None:
    normalized = value.strip().lower()
    assert normalized not in NONFINITE_TEXT, location
    if not normalized:
        return
    try:
        numeric = float(normalized)
    except ValueError:
        return
    assert math.isfinite(numeric), location


def _optional_float(value: str) -> float | None:
    return None if value == "" else float(value)


def test_repository_contains_exactly_the_nine_aggregate_results_and_report() -> None:
    assert {path.name for path in RESULTS_ROOT.iterdir() if path.is_file()} == EXPECTED_RESULT_FILES
    assert REPORT_PATH.is_file()
    assert REPORT_PATH.stat().st_size > 0

    for filename, expected_count in EXPECTED_ROW_COUNTS.items():
        assert len(_read_csv(RESULTS_ROOT / filename)) == expected_count


def test_all_aggregate_artifacts_share_the_frozen_provenance_labels() -> None:
    contract = _read_json(CONTRACT_PATH)
    summary = _read_json(RESULTS_ROOT / "metrics_summary.json")
    fingerprints = _read_json(RESULTS_ROOT / "data_fingerprints.json")
    request_audit = _read_json(RESULTS_ROOT / "request_audit_summary.json")

    assert {key: summary[key] for key in LABEL_KEYS} == EXPECTED_LABELS
    assert {key: contract[key] for key in LABEL_KEYS if key != "run_id"} == {
        key: EXPECTED_LABELS[key] for key in LABEL_KEYS if key != "run_id"
    }
    for document in (fingerprints, request_audit):
        assert {key: document[key] for key in LABEL_KEYS} == EXPECTED_LABELS

    for filename in EXPECTED_RESULT_FILES:
        if not filename.endswith(".csv"):
            continue
        for row_number, row in enumerate(_read_csv(RESULTS_ROOT / filename), start=2):
            assert {key: row[key] for key in LABEL_KEYS} == EXPECTED_LABELS, (
                filename,
                row_number,
            )


def test_aggregate_results_are_finite_and_exclude_forbidden_identifier_fields() -> None:
    for filename in EXPECTED_RESULT_FILES:
        path = RESULTS_ROOT / filename
        if filename.endswith(".json"):
            document = _read_json(path)
            _assert_finite(document, location=filename)
            assert_aggregate_mapping(document, location=filename)
            continue

        for row_number, row in enumerate(_read_csv(path), start=2):
            assert_aggregate_mapping(row, location=f"{filename}:{row_number}")
            for column, value in row.items():
                _assert_csv_cell_is_finite(
                    value,
                    location=f"{filename}:{row_number}:{column}",
                )


def test_primary_metrics_equal_the_basic_cost_rows() -> None:
    summary = _read_json(RESULTS_ROOT / "metrics_summary.json")
    cost_rows = _read_csv(RESULTS_ROOT / "cost_sensitivity.csv")
    basic_rows = {
        row["universe_id"]: row for row in cost_rows if row["cost_scenario"] == "basic"
    }

    assert set(basic_rows) == set(summary["universes"])
    assert len(basic_rows) == 4
    for universe_id, universe in summary["universes"].items():
        primary = universe["primary"]
        basic = basic_rows[universe_id]
        assert basic["path_policy"] == "conservative"
        assert basic["terminal_policy"] == "haircut_20"
        for key, expected in primary.items():
            assert key in basic
            if expected is None:
                assert basic[key] == ""
            elif isinstance(expected, int):
                assert int(basic[key]) == expected
            else:
                assert float(basic[key]) == pytest.approx(expected)


def test_economic_gate_recomputes_from_primary_split_and_concentration_outputs() -> None:
    summary = _read_json(RESULTS_ROOT / "metrics_summary.json")
    split_rows = _read_csv(RESULTS_ROOT / "split_metrics.csv")
    concentration_rows = _read_csv(RESULTS_ROOT / "concentration_metrics.csv")

    normalized_splits: list[dict[str, Any]] = []
    for row in split_rows:
        normalized = dict(row)
        normalized["expectancy_per_trade"] = _optional_float(row["expectancy_per_trade"])
        normalized["profit_factor"] = _optional_float(row["profit_factor"])
        normalized_splits.append(normalized)

    normalized_concentration: list[dict[str, Any]] = []
    for row in concentration_rows:
        normalized = dict(row)
        normalized["top_bucket_trade_share"] = _optional_float(
            row["top_bucket_trade_share"]
        )
        normalized_concentration.append(normalized)

    recomputed = economic_gate(
        {
            universe_id: universe["primary"]
            for universe_id, universe in summary["universes"].items()
        },
        normalized_splits,
        normalized_concentration,
    )
    recorded = summary["economic_gate"]

    assert recomputed["verdict"] == recorded["verdict"] == "MIXED"
    assert recomputed["effect"] == recorded["effect"]
    for universe_id in ("U50_PIT_LITE", "U100_PIT_LITE"):
        assert recomputed["universes"][universe_id]["criteria"] == recorded["universes"][
            universe_id
        ]["criteria"]
        assert recomputed["universes"][universe_id]["criteria_passed"] == 6
        assert recomputed["universes"][universe_id]["criteria_total"] == 11
        assert recomputed["universes"][universe_id]["verdict"] == "MIXED"
        assert recomputed["universes"][universe_id][
            "maximum_drawdown_delta_vs_u15"
        ] == pytest.approx(
            recorded["universes"][universe_id]["maximum_drawdown_delta_vs_u15"]
        )


def test_request_audit_totals_and_limits_are_internally_consistent() -> None:
    contract = _read_json(CONTRACT_PATH)
    audit = _read_json(RESULTS_ROOT / "request_audit_summary.json")
    fingerprints = _read_json(RESULTS_ROOT / "data_fingerprints.json")
    summary = _read_json(RESULTS_ROOT / "metrics_summary.json")

    assert sum(audit["endpoint_attempt_counts"].values()) == audit["attempts_used"]
    assert sum(audit["http_status_counts"].values()) == audit["attempts_used"]
    assert (
        audit["attempts_used"] + audit["external_prior_attempts"]
        == audit["gate_attempts_used"]
    )
    assert (
        audit["run_remaining_attempt_limit"] + audit["external_prior_attempts"]
        == audit["absolute_gate_attempt_limit"]
    )
    assert audit["absolute_gate_attempt_limit"] == contract["api"]["hard_attempt_limit"]
    assert audit["attempts_used"] <= audit["run_remaining_attempt_limit"]
    assert (
        audit["external_prior_attempts"] + audit["planned_worst_case_attempts"]
        <= audit["absolute_gate_attempt_limit"]
    )
    assert audit["implicit_retries"] == 0
    assert audit["single_threaded"] is True
    assert audit["rank_method"] == "single_session_no_retry"
    assert audit["filevault_gate_passed_before_acquisition"] is True
    assert audit["filevault_active_at_comparison"] is True
    assert audit["credential_recorded"] is False
    assert audit["raw_licensed_data_committed"] is False
    assert fingerprints["raw_licensed_data_committed"] is False
    assert summary["raw_licensed_data_committed"] is False


def test_production_fingerprint_and_report_authorization_state_are_frozen() -> None:
    contract = _read_json(CONTRACT_PATH)
    fingerprints = _read_json(RESULTS_ROOT / "data_fingerprints.json")
    summary = _read_json(RESULTS_ROOT / "metrics_summary.json")
    report = REPORT_PATH.read_text(encoding="utf-8")
    production_hashes = contract["production_sha256"]

    assert len(production_hashes) == 19
    assert fingerprints["production_sha_expected_count"] == 19
    assert fingerprints["production_sha_match_count"] == 19
    assert summary["production_sha_match"] == "19/19"
    for relative_path, expected_sha256 in production_hashes.items():
        actual_sha256 = hashlib.sha256(
            (REPOSITORY_ROOT / relative_path).read_bytes()
        ).hexdigest()
        assert actual_sha256 == expected_sha256, relative_path

    assert summary["economic_gate"]["verdict"] == "MIXED"
    assert summary["authorizations"]["formal_u50_u100"] == "NOT_AUTHORIZED"
    assert summary["authorizations"]["formal_candidate"] == "HOLD"
    assert summary["authorizations"]["real_money_canary"] == "none"
    assert summary["authorizations"]["purchase_or_plan_change"] is False
    assert summary["private_cleanup"] == "NOT_EXECUTED"

    for key in ("gate_id", "base_commit", "run_id", "classification"):
        assert EXPECTED_LABELS[key] in report
    assert "- Overall: **MIXED**" in report
    assert "- U50_PIT_LITE: **MIXED** (6/11 criteria" in report
    assert "- U100_PIT_LITE: **MIXED** (6/11 criteria" in report
    assert "- Formal U50/U100: not authorized" in report
    assert "- Formal Candidate: HOLD" in report
    assert "- Real-money canary: none" in report
    assert "cleanup remains NOT_EXECUTED" in report
    assert "The complete delisted-issue population is not guaranteed." in report
    assert "U15 adjusted/static is survivorship-biased" in report
    for filename in EXPECTED_RESULT_FILES:
        assert f"({f'../results/{filename}'})" in report
