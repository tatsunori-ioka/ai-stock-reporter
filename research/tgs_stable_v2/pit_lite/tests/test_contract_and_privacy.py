from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pit_lite.artifacts import write_csv, write_json
from pit_lite.contract import (
    BASE_COMMIT,
    CLASSIFICATION,
    CONTRACT,
    GATE_ID,
    PIT_ROOT,
    verify_production_files,
    verify_protected_inputs,
)
from pit_lite.safety import SafetyError, assert_aggregate_mapping


EXPECTED_BASE = "d3b8ed0ec09d6d7fc70aeca5144f8bb6962c4073"
ALLOWED_RESULTS = {
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


def test_contract_freezes_gate_scope_and_authorization_boundaries() -> None:
    assert GATE_ID == "V2-R2A_PIT_LITE_UNIVERSE_COMPARISON"
    assert BASE_COMMIT == EXPECTED_BASE
    assert CLASSIFICATION == "PIT_LITE_EXPLORATORY_ONLY_NOT_FORMAL_CANDIDATE"
    authorizations = CONTRACT["authorizations"]
    assert authorizations == {
        "pit_lite_u15_u50_u100_execution": True,
        "formal_u50_u100_execution": False,
        "formal_candidate_promotion": False,
        "real_money_canary": "none",
        "purchase_or_plan_change": False,
        "production_change": False,
        "private_data_cleanup_in_this_gate": False,
    }


def test_contract_freezes_api_budget_endpoints_and_retry_policy() -> None:
    api = CONTRACT["api"]
    assert api["hard_attempt_limit"] == 3000
    assert api["maximum_retries_per_page"] == 2
    assert api["retry_http_statuses"] == [429, "500-599"]
    assert api["backoff_seconds"] == [1.0, 2.0]
    assert api["single_threaded"] is True
    assert set(api["allowed_endpoints"]) == {
        "/markets/calendar",
        "/equities/master",
        "/equities/bars/daily",
    }
    assert CONTRACT["period"]["frozen_end_date"] == "2026-07-24"
    assert (
        api["rank_window_fallback"]["planned_worst_case_attempts"]
        == 2373
    )


def test_contract_freezes_primary_portfolio_and_path_semantics() -> None:
    portfolio = CONTRACT["portfolio"]
    tgs = CONTRACT["tgs"]
    assert portfolio["initial_capital_jpy"] == 10_000_000
    assert portfolio["maximum_concurrent_positions"] == 10
    assert portfolio["maximum_position_fraction_of_open_equity"] == 0.10
    assert portfolio["fractional_shares"] is True
    assert portfolio["leverage"] is False
    assert portfolio["shorting"] is False
    assert portfolio["entry_priority"] == [
        "score_desc",
        "signal_date_60_session_median_Va_desc",
        "code_asc",
    ]
    assert tgs["entry"] == "next JPX market session Open"
    assert tgs["same_day_path_primary"] == "conservative_stop_first"
    assert tgs["same_day_path_sensitivity"] == "optimistic_take_first"
    assert tgs["gap_fill"] == "Open"
    assert tgs["maximum_holding_ticker_sessions"] == 60


def test_protected_input_hashes_are_exact() -> None:
    verified = verify_protected_inputs()
    assert verified == CONTRACT["protected_inputs_sha256"]
    assert len(verified) == 6


def test_production_hashes_are_exact_19_of_19() -> None:
    verified = verify_production_files()
    assert verified == CONTRACT["production_sha256"]
    assert len(verified) == 19


@pytest.mark.parametrize(
    "forbidden",
    [
        {"ticker": "1234"},
        {"code": "12340"},
        {"members": ["12340"]},
        {"trades": [{"profit": 1.0}]},
        {"entry_date": "2024-01-01"},
        {"AdjClose": 123.0},
        {"nested": {"raw_response": "licensed"}},
    ],
)
def test_aggregate_mapping_rejects_reconstructible_or_identifying_fields(
    forbidden: dict[str, object],
) -> None:
    with pytest.raises(SafetyError):
        assert_aggregate_mapping(forbidden)


def test_aggregate_mapping_allows_only_nonidentifying_aggregates() -> None:
    assert_aggregate_mapping(
        {
            "universe_id": "U50_PIT_LITE",
            "cagr": 0.12,
            "maximum_drawdown": -0.20,
            "composition_sha256": "a" * 64,
            "annual": [{"year": 2024, "selected_count": 50}],
        }
    )


def test_artifact_writers_fail_closed_before_writing_forbidden_content(
    tmp_path: Path,
) -> None:
    json_path = tmp_path / "bad.json"
    csv_path = tmp_path / "bad.csv"
    with pytest.raises(SafetyError):
        write_json(json_path, {"ticker": "1234.T"})
    with pytest.raises(SafetyError):
        write_csv(csv_path, [{"universe_id": "U50", "code": "12340"}])
    assert not json_path.exists()
    assert not csv_path.exists()


def test_artifact_writers_emit_deterministic_valid_aggregates(tmp_path: Path) -> None:
    json_path = tmp_path / "aggregate.json"
    csv_path = tmp_path / "aggregate.csv"
    payload = {"z": 2, "a": {"metric": 1}}
    write_json(json_path, payload)
    write_csv(
        csv_path,
        [
            {"universe_id": "U50", "year": 2024, "selected_count": 50},
            {"universe_id": "U100", "year": 2024, "selected_count": 100},
        ],
    )
    assert json.loads(json_path.read_text(encoding="utf-8")) == payload
    assert json_path.read_text(encoding="utf-8").index('"a"') < json_path.read_text(
        encoding="utf-8"
    ).index('"z"')
    assert csv_path.read_text(encoding="utf-8").splitlines()[0] == (
        "universe_id,year,selected_count"
    )


def test_csv_writer_accepts_reordered_same_keys_but_rejects_different_key_sets(
    tmp_path: Path,
) -> None:
    accepted = tmp_path / "reordered.csv"
    write_csv(
        accepted,
        [
            {"universe_id": "U50", "year": 2024, "selected_count": 50},
            {"selected_count": 100, "universe_id": "U100", "year": 2024},
        ],
    )
    assert accepted.read_text(encoding="utf-8").splitlines() == [
        "universe_id,year,selected_count",
        "U50,2024,50",
        "U100,2024,100",
    ]
    rejected = tmp_path / "different-keys.csv"
    with pytest.raises(SafetyError, match="identical"):
        write_csv(
            rejected,
            [
                {"universe_id": "U50", "year": 2024},
                {"universe_id": "U100", "selected_count": 100},
            ],
        )
    assert not rejected.exists()


def test_repository_results_directory_is_allowlisted_and_nonreconstructible() -> None:
    results = PIT_ROOT / "results"
    if not results.exists():
        return
    files = {path.name for path in results.iterdir() if path.is_file()}
    assert files <= ALLOWED_RESULTS
    assert not any(path.is_dir() for path in results.iterdir())
    forbidden_names = {
        "raw",
        "normalized",
        "bars",
        "trade_ledger",
        "universe_membership",
        "request_cache",
    }
    assert not (files & forbidden_names)
    for path in results.iterdir():
        if path.suffix == ".json":
            assert_aggregate_mapping(json.loads(path.read_text(encoding="utf-8")))
        elif path.suffix == ".csv":
            with path.open(encoding="utf-8", newline="") as source:
                for row in csv.DictReader(source):
                    assert_aggregate_mapping(row)


def test_private_data_categories_do_not_exist_inside_repository_tree() -> None:
    forbidden_directories = {
        "raw",
        "request_cache",
        "trade_ledger",
        "universe_membership",
    }
    assert not [
        path
        for path in PIT_ROOT.rglob("*")
        if path.is_dir()
        and path.name in forbidden_directories
        and "tests" not in path.parts
    ]


def test_contract_repository_output_allowlist_matches_implementation_test() -> None:
    assert set(CONTRACT["aggregate_output_policy"]["allowed_repository_results"]) == (
        ALLOWED_RESULTS
    )
    assert CONTRACT["license_boundary"]["repository_raw_data"] is False
    assert CONTRACT["license_boundary"]["repository_reconstructible_data"] is False
