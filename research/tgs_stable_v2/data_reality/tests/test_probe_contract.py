from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import urllib.parse
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Mapping

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "probe_jquants_v2.py"
RESULTS = Path(__file__).parents[1] / "results"
SPEC = importlib.util.spec_from_file_location("probe_jquants_v2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


def _master_row(date: str, code: str) -> dict[str, Any]:
    return {
        "Date": date,
        "Code": code,
        "CoName": "DO_NOT_LEAK_COMPANY_NAME",
        "CoNameEn": "DO_NOT_LEAK_COMPANY_NAME_EN",
        "S17": "1",
        "S17Nm": "sector",
        "S33": "0050",
        "S33Nm": "sector33",
        "ScaleCat": "TOPIX Core30",
        "Mkt": "0111",
        "MktNm": "Prime",
        "Mrgn": "1",
        "MrgnNm": "margin",
        "ProdCat": "01",
    }


def _bar_rows(code: str, factor: float = 0.5) -> list[dict[str, Any]]:
    previous_adjusted_close = 100.0 * factor
    current_open = 100.0 * factor
    return [
        {
            "Date": "2024-03-27",
            "Code": code,
            "O": 98.0,
            "H": 101.0,
            "L": 97.0,
            "C": 100.0,
            "Vo": 1000,
            "Va": 100000,
            "AdjFactor": 1.0,
            "AdjO": 98.0 * factor,
            "AdjH": 101.0 * factor,
            "AdjL": 97.0 * factor,
            "AdjC": previous_adjusted_close,
            "AdjVo": 1000.0 / factor,
        },
        {
            "Date": "2024-03-28",
            "Code": code,
            "O": current_open,
            "H": current_open * 1.02,
            "L": current_open * 0.98,
            "C": current_open,
            "Vo": 2000,
            "Va": 100000,
            "AdjFactor": factor,
            "AdjO": current_open,
            "AdjH": current_open * 1.02,
            "AdjL": current_open * 0.98,
            "AdjC": current_open,
            "AdjVo": 2000,
        },
    ]


class StaticTransport:
    def __init__(self, responses: list[probe.HttpResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> probe.HttpResponse:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "timeout_seconds": timeout_seconds,
            }
        )
        if not self.responses:
            raise AssertionError("unexpected transport call")
        return self.responses.pop(0)


class PlanTransport:
    """Synthetic provider for the complete nine-probe plan."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> probe.HttpResponse:
        self.calls.append({"url": url, "headers": dict(headers)})
        parsed = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path.endswith("/equities/master"):
            requested = query.get("date", ["latest"])[0]
            date = "2026-07-27" if requested == "latest" else (
                f"{requested[:4]}-{requested[4:6]}-{requested[6:]}"
            )
            codes = ["86970", "70110", "84110"]
            if requested in {"20100401", "20150401", "20200401"}:
                codes.append("78290")
            rows = [_master_row(date, code) for code in codes]
        elif parsed.path.endswith("/equities/bars/daily"):
            code = query["code"][0]
            if code == "84110":
                rows = _bar_rows(code, factor=10.0)
            elif code == "70110":
                rows = _bar_rows(code, factor=0.1)
            elif code == "78290":
                rows = _bar_rows(code, factor=1.0)
            else:
                rows = _bar_rows(code, factor=0.5)
        else:
            raise AssertionError(f"unexpected endpoint: {parsed.path}")
        return probe.HttpResponse(
            status=200,
            body=json.dumps({"data": rows}).encode("utf-8"),
        )


def _client(
    transport: Any,
    *,
    limit: int = probe.MAX_API_REQUESTS,
) -> tuple[Any, Any]:
    budget = probe.RequestBudget(limit)
    client = probe.SafeApiClient(
        "unit-test-sentinel",
        transport=transport,
        budget=budget,
        rate_limiter=probe.RateLimiter(0),
    )
    return client, budget


def test_import_contract_is_get_only_and_hard_capped() -> None:
    assert probe.MAX_API_REQUESTS == 30
    assert probe.ALLOWED_ENDPOINTS == {
        "/equities/master",
        "/equities/bars/daily",
    }
    assert probe.API_BASE.startswith("https://")


def test_default_execution_is_zero_network_zero_env_zero_write() -> None:
    class ExplodingEnvironment(dict[str, str]):
        def get(self, key: str, default: str = "") -> str:
            raise AssertionError("dry run must not inspect the environment")

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        result = probe.main([], environ=ExplodingEnvironment())
    payload = json.loads(stdout.getvalue())
    assert result == 0
    assert payload["network_requests"] == 0
    assert payload["files_written"] == 0
    assert payload["authentication_read"] is False
    assert payload["u50_u100_backtest"] == "not_in_scope"


def test_missing_api_key_fails_without_echoing_any_secret() -> None:
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        result = probe.main(
            ["--live", "--audit-as-of", "2026-07-26"],
            environ={},
        )
    assert result == 2
    assert "JQUANTS_API_KEY is not set" in stderr.getvalue()
    assert "x-api-key" not in stderr.getvalue()


def test_request_budget_rejects_thirty_first_before_transport() -> None:
    response = probe.HttpResponse(status=200, body=b'{"data":[]}')
    transport = StaticTransport([response] * 30)
    client, budget = _client(transport, limit=30)
    with tempfile.TemporaryDirectory() as directory:
        raw = Path(directory)
        for number in range(30):
            client.get_paginated(
                "/equities/master",
                {"date": f"202601{number + 1:02d}"},
                raw_directory=raw,
                probe_id=f"budget-{number}",
            )
        with pytest.raises(probe.RequestLimitExceeded):
            client.get_paginated(
                "/equities/master",
                {},
                raw_directory=raw,
                probe_id="budget-overflow",
            )
    assert budget.used == 30
    assert len(transport.calls) == 30


def test_prior_failed_attempts_are_preserved_in_budget() -> None:
    budget = probe.RequestBudget(30, initial_used=1)
    assert budget.used == 1
    assert budget.consume() == 2


def test_request_uses_secret_header_not_url() -> None:
    secret = "unit-test-sentinel"
    transport = StaticTransport(
        [probe.HttpResponse(status=200, body=b'{"data":[]}')]
    )
    client, _ = _client(transport)
    with tempfile.TemporaryDirectory() as directory:
        client.get_paginated(
            "/equities/master",
            {"date": "20200401"},
            raw_directory=Path(directory),
            probe_id="header",
        )
    assert transport.calls[0]["headers"]["x-api-key"] == secret
    assert secret not in transport.calls[0]["url"]


def test_pagination_aggregates_pages_and_counts_every_attempt() -> None:
    first = json.dumps(
        {"data": [_master_row("2020-04-01", "11110")], "pagination_key": "p2"}
    ).encode()
    second = json.dumps(
        {"data": [_master_row("2020-04-01", "22220")]}
    ).encode()
    transport = StaticTransport(
        [
            probe.HttpResponse(status=200, body=first),
            probe.HttpResponse(status=200, body=second),
        ]
    )
    client, budget = _client(transport)
    with tempfile.TemporaryDirectory() as directory:
        rows, metadata = client.get_paginated(
            "/equities/master",
            {"date": "20200401"},
            raw_directory=Path(directory),
            probe_id="pages",
        )
    assert len(rows) == 2
    assert metadata["status"] == "ok"
    assert metadata["pagination_complete"] is True
    assert budget.used == 2
    assert "pagination_key=p2" in transport.calls[1]["url"]


def test_pagination_cycle_fails_closed() -> None:
    body = json.dumps(
        {"data": [_master_row("2020-04-01", "11110")], "pagination_key": "same"}
    ).encode()
    transport = StaticTransport(
        [
            probe.HttpResponse(status=200, body=body),
            probe.HttpResponse(status=200, body=body),
        ]
    )
    client, budget = _client(transport)
    with tempfile.TemporaryDirectory() as directory:
        _, metadata = client.get_paginated(
            "/equities/master",
            {"date": "20200401"},
            raw_directory=Path(directory),
            probe_id="cycle",
        )
    assert metadata["status"] == "pagination_cycle"
    assert budget.used == 2


@pytest.mark.parametrize(
    ("http_status", "expected"),
    [(401, "auth_failed"), (403, "entitlement_denied"), (429, "rate_limited")],
)
def test_http_failures_are_classified_without_retry(
    http_status: int, expected: str
) -> None:
    transport = StaticTransport(
        [
            probe.HttpResponse(
                status=http_status,
                body=b'{"message":"DO_NOT_LEAK_PROVIDER_MESSAGE"}',
            )
        ]
    )
    client, budget = _client(transport)
    with tempfile.TemporaryDirectory() as directory:
        _, metadata = client.get_paginated(
            "/equities/master",
            {},
            raw_directory=Path(directory),
            probe_id="failure",
        )
    assert metadata["status"] == expected
    assert budget.used == 1
    assert len(transport.calls) == 1
    assert "DO_NOT_LEAK" not in json.dumps(metadata)


def test_unknown_fields_tolerated_but_required_field_missing_is_schema_mismatch() -> None:
    rows = [_master_row("2020-04-01", "11110")]
    rows[0]["FutureField"] = "accepted"
    del rows[0]["Mkt"]
    metadata = {
        "status": "ok",
        "request_count": 1,
        "page_count": 1,
        "requests": [{"http_status": 200}],
        "response_bytes": 10,
        "response_sha256": "a" * 64,
        "pagination_complete": True,
    }
    result = probe._summarize_rows(
        rows,
        metadata,
        probe_id="schema",
        endpoint="/equities/master",
        parameters={},
        required_fields=probe.MASTER_REQUIRED_FIELDS,
    )
    assert "FutureField" in result["fields"]
    assert result["status"] == "schema_mismatch"
    assert result["missing_required_fields"] == ["Mkt"]


def test_all_null_required_field_is_schema_mismatch() -> None:
    rows = [_master_row("2020-04-01", "11110")]
    rows[0]["Mkt"] = None
    metadata = {
        "status": "ok",
        "request_count": 1,
        "page_count": 1,
        "requests": [{"http_status": 200}],
        "response_bytes": 10,
        "response_sha256": "a" * 64,
        "pagination_complete": True,
    }
    result = probe._summarize_rows(
        rows,
        metadata,
        probe_id="all-null",
        endpoint="/equities/master",
        parameters={"date": "20200401"},
        required_fields=probe.MASTER_REQUIRED_FIELDS,
    )
    assert result["status"] == "schema_mismatch"
    assert result["missing_required_fields"] == []
    assert result["all_null_required_fields"] == ["Mkt"]


def test_complete_plan_is_sanitized_and_deletes_raw_temp_files() -> None:
    transport = PlanTransport()
    with tempfile.TemporaryDirectory() as parent:
        temp_root = Path(parent)
        summary, matrix = probe.run_live_probe(
            "unit-test-sentinel",
            audit_as_of="2026-07-26",
            transport=transport,
            min_interval_seconds=0,
            temp_root=temp_root,
        )
        assert list(temp_root.iterdir()) == []
    encoded = json.dumps({"summary": summary, "matrix": matrix})
    assert "unit-test-sentinel" not in encoded
    assert "DO_NOT_LEAK_COMPANY_NAME" not in encoded
    assert summary["api_calls"]["used"] == 9
    assert summary["raw_response_handling"]["files_created"] == 9
    assert summary["raw_response_handling"]["retained"] is False
    assert len(transport.calls) == 9


def test_repository_temp_root_is_rejected_before_network() -> None:
    transport = PlanTransport()
    with pytest.raises(probe.OutputPathError):
        probe.run_live_probe(
            "unit-test-sentinel",
            audit_as_of="2026-07-26",
            transport=transport,
            min_interval_seconds=0,
            temp_root=probe.DATA_REALITY_ROOT,
        )
    assert transport.calls == []


def test_delisted_example_is_verified_without_full_issue_list() -> None:
    with tempfile.TemporaryDirectory() as parent:
        summary, _ = probe.run_live_probe(
            "unit-test-sentinel",
            audit_as_of="2026-07-26",
            transport=PlanTransport(),
            min_interval_seconds=0,
            temp_root=Path(parent),
        )
    evidence = summary["delisted_issue_example"]
    assert evidence["code"] == "78290"
    assert evidence["present_in_2020_04_01_master"] is True
    assert evidence["present_in_latest_master"] is False
    assert evidence["historical_presence_verified"] is True
    assert "rows" not in json.dumps(summary)


def test_matrix_fails_closed_on_legal_snapshot_requirement() -> None:
    with tempfile.TemporaryDirectory() as parent:
        summary, matrix = probe.run_live_probe(
            "unit-test-sentinel",
            audit_as_of="2026-07-26",
            transport=PlanTransport(),
            min_interval_seconds=0,
            temp_root=Path(parent),
        )
    by_id = {item["id"]: item for item in matrix["capabilities"]}
    assert by_id["reproducible_historical_snapshot"]["status"] == (
        "SUPPORT_CONFIRMATION_REQUIRED"
    )
    assert matrix["capability_verdict"] == "PRO_OR_ALTERNATIVE_REQUIRED"
    assert matrix["formal_u50_u100_possible"] is False
    assert (
        matrix["formal_u50_u100_possible_with_current_personal_v2"] is False
    )
    assert matrix["formal_u50_u100_authorized"] is False
    assert {
        "delisted_issue_inclusion",
        "listing_date",
        "delisting_date",
        "five_year_listing_history_eligibility",
        "security_product_category",
        "historical_market_regime_mapping",
        "ticker_lineage_or_stable_security_id",
        "historical_corporate_group_mapping",
        "special_treatment_or_untradeable_status",
        "corporate_action_adjustment_factor",
        "reproducible_historical_snapshot",
        "known_at_or_available_at_timestamp",
    }.issubset(set(matrix["critical_failures"]))
    assert matrix["u15_adjusted_rerun"]["formal_capability_possible"] is False
    assert matrix["u15_adjusted_rerun"][
        "comprehensive_common_period_rerun_possible"
    ] is False
    assert matrix["u15_adjusted_rerun"][
        "split_reverse_split_adjusted_common_period_rerun_possible"
    ] is True
    assert matrix["u15_adjusted_rerun"]["full_frozen_period_possible"] is False
    assert matrix["u15_adjusted_rerun"][
        "formal_corporate_action_complete"
    ] is False
    assert matrix["u15_adjusted_rerun"][
        "comprehensive_corporate_action_coverage_established"
    ] is False
    assert summary["decision"]["capability_verdict"] == matrix[
        "capability_verdict"
    ]


def test_adjustment_capability_fails_closed_on_inconsistent_evidence() -> None:
    with tempfile.TemporaryDirectory() as parent:
        summary, _ = probe.run_live_probe(
            "unit-test-sentinel",
            audit_as_of="2026-07-26",
            transport=PlanTransport(),
            min_interval_seconds=0,
            temp_root=Path(parent),
        )
    summary["daily_bars"]["probes"][0]["corporate_action_metrics"][
        "official_factor_match"
    ] = False
    matrix = probe.build_capability_matrix(summary)
    by_id = {item["id"]: item for item in matrix["capabilities"]}
    assert by_id["corporate_action_adjustment_factor"]["status"] == (
        "PREMIUM_UNKNOWN"
    )
    assert matrix["u15_adjusted_rerun"][
        "split_reverse_split_adjusted_common_period_rerun_possible"
    ] is False


def test_historical_master_requires_requested_response_date_match() -> None:
    with tempfile.TemporaryDirectory() as parent:
        summary, _ = probe.run_live_probe(
            "unit-test-sentinel",
            audit_as_of="2026-07-26",
            transport=PlanTransport(),
            min_interval_seconds=0,
            temp_root=Path(parent),
        )
    summary["listed_issue_master"]["probes"][0][
        "requested_snapshot_date_match"
    ] = False
    matrix = probe.build_capability_matrix(summary)
    by_id = {item["id"]: item for item in matrix["capabilities"]}
    assert by_id["point_in_time_active_issue_master"]["status"] == (
        "PREMIUM_UNKNOWN"
    )


def test_corporate_action_checks_split_and_reverse_split_continuity() -> None:
    split = probe._corporate_action_metrics(_bar_rows("86970", factor=0.5))
    reverse = probe._corporate_action_metrics(_bar_rows("84110", factor=10.0))
    assert split["adjustment_factor_non_one_count"] == 1
    assert split["all_observed_boundaries_consistent"] is True
    assert reverse["adjustment_factor_non_one_count"] == 1
    assert reverse["all_observed_boundaries_consistent"] is True


def test_output_path_cannot_escape_data_reality_results() -> None:
    with pytest.raises(probe.OutputPathError):
        probe._validated_output_path(Path("/tmp/jquants_probe_summary.json"))


def test_url_allowlist_rejects_nonofficial_host_and_unknown_path() -> None:
    with pytest.raises(probe.UnsafeRequest):
        probe.validate_url("https://example.com/v2/equities/master")
    with pytest.raises(probe.UnsafeRequest):
        probe.validate_url("https://api.jquants.com/v2/orders")


def test_committed_sanitized_artifacts_are_internally_consistent() -> None:
    summary = json.loads(
        (RESULTS / "jquants_probe_summary.json").read_text(encoding="utf-8")
    )
    matrix = json.loads(
        (RESULTS / "jquants_capability_matrix.json").read_text(encoding="utf-8")
    )
    assert summary["base_commit"] == probe.BASE_COMMIT
    assert summary["audit_id"] == matrix["audit_id"]
    assert summary["api_calls"]["used"] == matrix["api_call_count"]
    assert summary["api_calls"]["used"] <= probe.MAX_API_REQUESTS
    assert summary["api_calls"]["prior_failed_attempts"] == 1
    assert summary["authentication"]["secret_recorded"] is False
    assert summary["raw_response_handling"]["retained"] is False
    assert summary["raw_response_handling"]["inside_repository"] is False
    assert summary["decision"]["capability_verdict"] == matrix[
        "capability_verdict"
    ]
    assert summary["official_sources"] == list(probe.OFFICIAL_SOURCES)
    assert summary["legal_classification"] == probe._legal_classification()
    assert matrix == probe.build_capability_matrix(summary)
    assert summary["decision"] == probe._decision_from_matrix(matrix)
    by_id = {item["id"]: item for item in matrix["capabilities"]}
    assert by_id["corporate_action_adjustment_factor"]["status"] == "PARTIAL"
    assert summary["legal_classification"][
        "ephemeral_local_processing_for_own_use"
    ] == "AVAILABLE_FOR_NONCOMMERCIAL_NONACADEMIC_PERSONAL_OWN_USE"
    source_ids = {item["id"] for item in summary["official_sources"]}
    assert len(source_ids) == len(summary["official_sources"])
    for capability in matrix["capabilities"]:
        for evidence in capability["evidence"]:
            if evidence.startswith("official:"):
                assert evidence.removeprefix("official:") in source_ids
    assert matrix["formal_u50_u100_possible"] is False
    assert (
        matrix["formal_u50_u100_possible_with_current_personal_v2"] is False
    )
    assert matrix["formal_u50_u100_authorized"] is False
    assert matrix["u50_u100_backtest_executed"] is False


def test_committed_live_evidence_covers_required_bounded_probes() -> None:
    summary = json.loads(
        (RESULTS / "jquants_probe_summary.json").read_text(encoding="utf-8")
    )
    master = summary["listed_issue_master"]["probes"]
    assert [item["probe_id"] for item in master] == [
        "master_2010_04_01",
        "master_2015_04_01",
        "master_2020_04_01",
        "master_2025_04_01",
        "master_latest",
    ]
    assert all(item["status"] == "ok" for item in master)
    assert all(item["row_count"] > 0 for item in master)
    assert summary["delisted_issue_example"][
        "historical_presence_verified"
    ] is True
    corporate_actions = [
        item
        for item in summary["daily_bars"]["probes"]
        if "corporate_action_metrics" in item
    ]
    assert len(corporate_actions) == 3
    assert all(
        item["corporate_action_metrics"][
            "adjustment_factor_non_one_count"
        ]
        > 0
        for item in corporate_actions
    )
    assert all(
        item["corporate_action_metrics"][
            "all_observed_boundaries_consistent"
        ]
        is True
        for item in corporate_actions
    )


def test_committed_results_contain_no_raw_response_container() -> None:
    for path in RESULTS.glob("*.json"):
        payload = path.read_text(encoding="utf-8")
        assert '"rows"' not in payload
        assert '"data"' not in payload
        assert "DO_NOT_LEAK" not in payload
        assert "JQUANTS_API_KEY=" not in payload
