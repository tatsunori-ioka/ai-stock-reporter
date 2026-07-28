from __future__ import annotations

import csv
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pit_lite.safety import assert_aggregate_mapping


ROOT_CAUSE_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = ROOT_CAUSE_ROOT / "results"
REPORT_PATH = ROOT_CAUSE_ROOT / "reports" / "ROOT_CAUSE_DIAGNOSTIC_REPORT.md"
EXPECTED_FILES = {
    "score_combination_metrics.csv",
    "exit_reason_metrics.csv",
    "capacity_attribution.csv",
    "drawdown_episode_summary.csv",
    "regime_summary.csv",
    "diagnostic_verdict.json",
    "private_input_fingerprints.json",
}
EXPECTED_PROVENANCE = {
    "gate_id": "V2-R2B_ROOT_CAUSE_DIAGNOSTIC_AND_STOP_DECISION",
    "model_id": "TGS_STABLE_V2_ROOT_CAUSE_DIAGNOSTIC",
    "base_commit": "9dae034999aa33b3f0d059adc059d3c8dbe659c2",
    "classification": "POST_HOC_ASSOCIATION_DIAGNOSTIC_ONLY",
    "source_run_id": "v2-r2a-20260727-d3b8ed0-integrity1",
}


def _json(name: str) -> dict[str, Any]:
    value = json.loads((RESULTS_ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _csv(name: str) -> list[dict[str, str]]:
    with (RESULTS_ROOT / name).open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        assert reader.fieldnames
        rows = list(reader)
    assert rows
    assert all(None not in row for row in rows)
    return rows


def _finite(value: Any) -> None:
    if isinstance(value, Mapping):
        for child in value.values():
            _finite(child)
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for child in value:
            _finite(child)
    elif isinstance(value, float):
        assert math.isfinite(value)


def test_exact_seven_aggregate_results_and_report_exist() -> None:
    assert {
        path.name for path in RESULTS_ROOT.iterdir() if path.is_file()
    } == EXPECTED_FILES
    assert REPORT_PATH.is_file()
    assert REPORT_PATH.stat().st_size > 1_000


def test_generated_csv_row_counts_are_frozen() -> None:
    assert len(_csv("score_combination_metrics.csv")) == 60
    assert len(_csv("exit_reason_metrics.csv")) == 252
    assert len(_csv("capacity_attribution.csv")) == 72
    assert len(_csv("drawdown_episode_summary.csv")) == 15
    assert len(_csv("regime_summary.csv")) == 12


def test_all_artifacts_have_the_same_provenance() -> None:
    for name in EXPECTED_FILES:
        if name.endswith(".json"):
            document = _json(name)
            assert {
                key: document[key] for key in EXPECTED_PROVENANCE
            } == EXPECTED_PROVENANCE
        else:
            for row in _csv(name):
                assert {
                    key: row[key] for key in EXPECTED_PROVENANCE
                } == EXPECTED_PROVENANCE


def test_json_and_csv_artifacts_are_finite_and_aggregate_only() -> None:
    for name in EXPECTED_FILES:
        if name.endswith(".json"):
            document = _json(name)
            _finite(document)
            assert_aggregate_mapping(document, location=name)
        else:
            for index, row in enumerate(_csv(name), start=2):
                assert_aggregate_mapping(row, location=f"{name}:{index}")
                for value in row.values():
                    assert value.strip().lower() not in {
                        "nan",
                        "inf",
                        "-inf",
                        "infinity",
                        "-infinity",
                    }


def test_no_exact_identifier_or_price_columns_are_published() -> None:
    forbidden = {
        "code",
        "ticker",
        "security_id",
        "symbol",
        "company",
        "name",
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
    for name in EXPECTED_FILES:
        if name.endswith(".csv"):
            headers = set(_csv(name)[0])
            assert headers.isdisjoint(forbidden)


def test_no_known_static_or_proposal_identifier_is_in_output_text() -> None:
    repository = ROOT_CAUSE_ROOT.parents[2]
    source_text = "\n".join(
        (repository / relative).read_text(encoding="utf-8")
        for relative in (
            "research/tgs_stable_v2/config/universe_u15.yaml",
            "research/tgs_stable_v2/config/universe_u50_proposal.yaml",
            "research/tgs_stable_v2/config/universe_u100_proposal.yaml",
        )
    )
    identifiers = set(re.findall(r"(?<![0-9])[0-9]{4}(?![0-9])", source_text))
    output_text = REPORT_PATH.read_text(encoding="utf-8") + "\n" + "\n".join(
        path.read_text(encoding="utf-8")
        for path in RESULTS_ROOT.iterdir()
        if path.is_file()
    )
    assert not any(
        re.search(rf"(?<![0-9]){re.escape(identifier)}(?![0-9])", output_text)
        for identifier in identifiers
    )


def test_no_credential_shaped_content_is_published() -> None:
    text = REPORT_PATH.read_text(encoding="utf-8") + "\n" + "\n".join(
        path.read_text(encoding="utf-8")
        for path in RESULTS_ROOT.iterdir()
        if path.is_file()
    )
    assert "JQUANTS_API_KEY" not in text
    assert not re.search(r"(?i)authorization\s*:\s*bearer", text)
    assert not re.search(r"(?i)(api[_-]?key|secret)\s*[=:]\s*[A-Za-z0-9_-]{16,}", text)


def test_score_output_covers_every_fixed_mask_per_universe_and_split() -> None:
    rows = _csv("score_combination_metrics.csv")
    assert {int(row["bitmask"]) for row in rows} == {15, 23, 29, 30, 31}
    assert {row["split"] for row in rows} == {
        "overall",
        "development",
        "validation",
        "final_holdout",
    }
    assert {row["universe_id"] for row in rows} == {
        "U15_ADJUSTED_STATIC",
        "U50_PIT_LITE",
        "U100_PIT_LITE",
    }
    assert all(row["bit_pattern"] == format(int(row["bitmask"]), "05b") for row in rows)


def test_exit_output_covers_all_frozen_reason_and_score_groups() -> None:
    rows = _csv("exit_reason_metrics.csv")
    assert {row["exit_reason_group"] for row in rows} == {
        "stop_loss",
        "stop_gap",
        "take_profit",
        "take_profit_gap",
        "max_holding",
        "data_end_or_haircut",
        "other",
    }
    assert {row["score_group"] for row in rows} == {"ALL", "90", "100", "120"}
    assert {row["split"] for row in rows} == {
        "overall",
        "validation",
        "final_holdout",
    }


def test_capacity_output_separates_accept_capacity_and_duplicate() -> None:
    rows = _csv("capacity_attribution.csv")
    assert {row["disposition_group"] for row in rows} == {
        "accepted_all",
        "accepted_binding",
        "capacity_rejected",
        "duplicate_rejected",
        "missing_next_session",
        "invalid_bar",
    }
    count_only = [
        row
        for row in rows
        if row["disposition_group"] in {
            "duplicate_rejected",
            "missing_next_session",
            "invalid_bar",
        }
    ]
    assert all(row["quality_scope"] == "COUNT_ONLY" for row in count_only)


def test_drawdown_output_has_five_reconciled_episodes_per_universe() -> None:
    rows = _csv("drawdown_episode_summary.csv")
    for universe_id in (
        "U15_ADJUSTED_STATIC",
        "U50_PIT_LITE",
        "U100_PIT_LITE",
    ):
        current = [row for row in rows if row["universe_id"] == universe_id]
        assert [int(row["episode_rank"]) for row in current] == [1, 2, 3, 4, 5]
        assert all(row["position_pnl_reconciled"] == "True" for row in current)


def test_regime_output_has_four_fixed_periods_per_universe() -> None:
    rows = _csv("regime_summary.csv")
    for universe_id in (
        "U15_ADJUSTED_STATIC",
        "U50_PIT_LITE",
        "U100_PIT_LITE",
    ):
        assert {
            row["split"] for row in rows if row["universe_id"] == universe_id
        } == {"overall", "development", "validation", "final_holdout"}


def test_verdict_is_no_actionable_and_cause_is_g() -> None:
    verdict = _json("diagnostic_verdict.json")
    assert verdict["diagnostic_verdict"] == "NO_ACTIONABLE_DIAGNOSTIC_HYPOTHESIS"
    assert verdict["underperformance_cause_classification"] == (
        "G_CLEAR_CAUSE_NOT_IDENTIFIED"
    )
    assert verdict["actionable_hypotheses"] == []
    assert verdict["recommendation"]["recommended_final_action"] == (
        "END_TGS_STABLE_V2_RESEARCH"
    )


def test_hypothesis_statuses_are_fail_closed() -> None:
    hypotheses = _json("diagnostic_verdict.json")["hypotheses"]
    assert hypotheses["A_ADDED_SIGNAL_QUALITY"]["status"] == (
        "EVALUATED_NOT_ACTIONABLE"
    )
    assert hypotheses["B_CAPACITY_PRIORITY"]["status"] == (
        "EVALUATED_NOT_ACTIONABLE"
    )
    assert hypotheses["C_HIGH_EXPOSURE"]["status"] == "INSUFFICIENT_SAMPLE"
    assert hypotheses["D_EXIT_ATTRIBUTION"]["status"] == (
        "EVALUATED_NOT_ACTIONABLE"
    )
    assert hypotheses["E_SCORE_MONOTONICITY"]["status"] == "INSUFFICIENT_SAMPLE"
    assert not any(
        item["passes_all_robust_conditions"] for item in hypotheses.values()
    )


def test_score120_is_descriptive_only_and_sample_insufficient() -> None:
    score = _json("diagnostic_verdict.json")["score_diagnostic"]
    assert score["score_monotonicity"] == "NOT_ESTABLISHED"
    assert score["score_120_diagnosis"] == (
        "INSUFFICIENT_SAMPLE_FOR_ROBUST_SCORE120_HYPOTHESIS"
    )
    assert all(
        count < 30
        for universe in score["score_120_closed_counts"].values()
        for count in universe.values()
    )


def test_integrity_and_runtime_audits_are_zero_and_matching() -> None:
    verdict = _json("diagnostic_verdict.json")
    assert verdict["runtime_audit"] == {
        "api_key_reads": 0,
        "network_calls": 0,
        "private_writes": 0,
        "provider_api_calls": 0,
    }
    integrity = verdict["integrity"]
    assert integrity["deterministic_same_private_cache_rerun"] == "PASS"
    assert integrity["production_sha_match"] == "19/19"
    assert integrity["protected_input_sha_match"] == "6/6"
    assert integrity["credential_scan"] == 0
    assert integrity["licensed_raw_scan"] == 0


def test_authorizations_remain_closed_in_generated_verdict() -> None:
    authorizations = _json("diagnostic_verdict.json")["authorizations"]
    assert authorizations["formal_candidate"] == "HOLD"
    assert authorizations["formal_u50_u100"] == "NOT_AUTHORIZED"
    assert authorizations["real_money_canary"] == "none"
    assert authorizations["new_rule_execution"] is False
    assert authorizations["parameter_optimization"] is False
    assert authorizations["private_cleanup"] == "NOT_EXECUTED"
    assert authorizations["production_change"] is False


def test_private_fingerprint_output_matches_manifest_and_replay() -> None:
    fingerprints = _json("private_input_fingerprints.json")
    private = fingerprints["private_input_fingerprint"]
    assert private["manifest_sha256"] == (
        "7212e777fb613a1ff0170c54298a21979019677c466800e6edd3f0e5f1ac6d7e"
    )
    assert private["manifest_entry_count"] == 2357
    assert private["production_sha_match"] == "19/19"
    assert private["protected_input_sha_match"] == "6/6"
    assert all(
        item["match"]
        for item in fingerprints["frozen_primary_replay"].values()
    )
    assert fingerprints["raw_licensed_data_committed"] is False


def test_report_records_post_hoc_stop_decision_and_no_authorization() -> None:
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "final holdout had already been observed" in report
    assert "do not prove causality" in report
    assert "NO_ACTIONABLE_DIAGNOSTIC_HYPOTHESIS" in report
    assert "END_TGS_STABLE_V2_RESEARCH" in report
    assert "Formal Candidate: HOLD" in report
    assert "Real-money canary: none" in report
    assert "Private cleanup: NOT_EXECUTED" in report
