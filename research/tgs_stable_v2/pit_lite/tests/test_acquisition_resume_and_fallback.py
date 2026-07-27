from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import pit_lite.acquisition as acquisition
from pit_lite.api import HttpStatusError, ResponseTooLarge
from pit_lite.universe import SelectionSchedule


RUN_ID = "synthetic-resume-001"
CODES = ("11110", "22220")


def bar_row(date: pd.Timestamp, code: str) -> dict[str, Any]:
    return {
        "Date": pd.Timestamp(date).date().isoformat(),
        "Code": code,
        "O": 500.0,
        "H": 510.0,
        "L": 490.0,
        "C": 505.0,
        "Vo": 1_000_000.0,
        "Va": 2_000_000_000.0,
        "AdjFactor": 1.0,
        "AdjO": 500.0,
        "AdjH": 510.0,
        "AdjL": 490.0,
        "AdjC": 505.0,
        "AdjVo": 1_000_000.0,
    }


def master_row(date: pd.Timestamp, code: str) -> dict[str, Any]:
    return {
        "Date": pd.Timestamp(date).date().isoformat(),
        "Code": code,
        "ProdCat": "011",
        "Mkt": "0111",
        "S33": "0050" if code == CODES[0] else "1050",
        "S33Nm": "synthetic sector",
        "CoName": "synthetic company",
    }


class FakeClient:
    def __init__(
        self,
        sessions: pd.DatetimeIndex,
        schedule: SelectionSchedule,
        *,
        first_range_error: BaseException | None = None,
        fail_history_code: str | None = None,
    ) -> None:
        self.sessions = sessions
        self.schedule = schedule
        self.first_range_error = first_range_error
        self.fail_history_code = fail_history_code
        self.calls: list[dict[str, Any]] = []

    def get_paginated(
        self,
        endpoint: str,
        parameters: dict[str, str],
        *,
        request_id: str,
        maximum_pages: int,
        maximum_retries: int = 2,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        self.calls.append(
            {
                "endpoint": endpoint,
                "parameters": dict(parameters),
                "request_id": request_id,
                "maximum_pages": maximum_pages,
                "maximum_retries": maximum_retries,
            }
        )
        if endpoint == "/markets/calendar":
            return (
                [
                    {"Date": date.date().isoformat(), "HolDiv": "1"}
                    for date in self.sessions
                ],
                {},
            )
        if endpoint == "/equities/master":
            cutoff = pd.Timestamp(self.schedule.cutoff_date)
            return ([master_row(cutoff, code) for code in CODES], {})
        if endpoint != "/equities/bars/daily":
            raise AssertionError(f"unexpected endpoint: {endpoint}")

        if "from" in parameters and "to" in parameters and "code" not in parameters:
            if self.first_range_error is not None:
                error = self.first_range_error
                self.first_range_error = None
                raise error
            start = pd.to_datetime(parameters["from"])
            end = pd.to_datetime(parameters["to"])
            dates = self.sessions[
                (self.sessions >= start) & (self.sessions <= end)
            ]
            return ([bar_row(date, CODES[0]) for date in dates], {})
        if "date" in parameters:
            date = pd.to_datetime(parameters["date"])
            return ([bar_row(date, CODES[0])], {})
        if "code" in parameters:
            code = parameters["code"]
            if code == self.fail_history_code:
                raise RuntimeError(f"synthetic interruption for {code}")
            return ([bar_row(date, code) for date in self.sessions], {})
        raise AssertionError(f"unexpected bar parameters: {parameters}")

    def sanitized_audit(self) -> dict[str, Any]:
        return {"attempts_used": len(self.calls), "credential_recorded": False}


@pytest.fixture
def compact_schedule(monkeypatch) -> tuple[pd.DatetimeIndex, SelectionSchedule]:
    sessions = pd.bdate_range("2023-12-01", periods=61)
    schedule = SelectionSchedule(
        year=2024,
        selection_date=sessions[60].date().isoformat(),
        cutoff_date=sessions[59].date().isoformat(),
        trailing_60_start=sessions[0].date().isoformat(),
        trailing_252_start=sessions[0].date().isoformat(),
    )
    monkeypatch.setattr(
        acquisition,
        "annual_selection_schedule",
        lambda _sessions: [schedule],
    )
    real_plan = acquisition.frozen_acquisition_plan()
    synthetic_plan = replace(
        real_plan,
        provider_earliest_date=sessions[0].date().isoformat(),
        frozen_end_date=sessions[-1].date().isoformat(),
        selection_start_year=2024,
        selection_end_year=2024,
    )
    monkeypatch.setattr(
        acquisition,
        "frozen_acquisition_plan",
        lambda: synthetic_plan,
    )
    return sessions, schedule


def test_new_checkpoint_freezes_all_resume_identity_fields_before_first_api_call(
    tmp_path: Path,
    compact_schedule: tuple[pd.DatetimeIndex, SelectionSchedule],
) -> None:
    run = tmp_path / "private" / "runs" / RUN_ID

    class StopAtFirstApi:
        calls = 0

        def get_paginated(self, *_args, **_kwargs):
            self.calls += 1
            raise RuntimeError("synthetic stop at first API call")

    client = StopAtFirstApi()
    with pytest.raises(RuntimeError, match="synthetic stop"):
        acquisition.acquire(
            client,
            RUN_ID,
            run,
            external_prior_attempts=7,
        )
    assert client.calls == 1
    checkpoint = json.loads(
        (run / "checkpoint" / "acquisition.json").read_text(encoding="utf-8")
    )
    assert checkpoint["run_id"] == RUN_ID
    assert checkpoint["plan_sha256"] == acquisition.frozen_acquisition_plan().sha256
    assert checkpoint["contract_sha256"] == acquisition.sha256_file(
        acquisition.CONTRACT_PATH
    )
    assert checkpoint["acquisition_implementation_sha256"] == (
        acquisition.acquisition_implementation_sha256()
    )
    assert checkpoint["external_prior_attempts"] == 7


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("run_id", "different-run-id"),
        ("plan_sha256", "0" * 64),
        ("contract_sha256", "1" * 64),
        ("acquisition_implementation_sha256", "2" * 64),
        ("external_prior_attempts", 8),
    ],
)
def test_resume_identity_mismatch_fails_before_any_api_call(
    tmp_path: Path,
    compact_schedule: tuple[pd.DatetimeIndex, SelectionSchedule],
    field: str,
    replacement: Any,
) -> None:
    run = tmp_path / "private" / "runs" / RUN_ID
    checkpoint_path = run / "checkpoint" / "acquisition.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint = {
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "plan_sha256": acquisition.frozen_acquisition_plan().sha256,
        "contract_sha256": acquisition.sha256_file(acquisition.CONTRACT_PATH),
        "acquisition_implementation_sha256": (
            acquisition.acquisition_implementation_sha256()
        ),
        "external_prior_attempts": 7,
        "stage": "created",
        "fetched_candidate_codes": [],
        "rank_method": "four_session_range",
    }
    checkpoint[field] = replacement
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")

    class ApiMustNotRun:
        calls = 0

        def get_paginated(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("resume integrity failure reached API")

    client = ApiMustNotRun()
    with pytest.raises(RuntimeError, match=field):
        acquisition.acquire(
            client,
            RUN_ID,
            run,
            external_prior_attempts=7,
        )
    assert client.calls == 0


@pytest.mark.parametrize("missing_boundary", ["first", "last"])
def test_calendar_must_match_frozen_first_and_last_session_exactly(
    tmp_path: Path,
    compact_schedule: tuple[pd.DatetimeIndex, SelectionSchedule],
    missing_boundary: str,
) -> None:
    sessions, schedule = compact_schedule
    wrong_sessions = sessions[1:] if missing_boundary == "first" else sessions[:-1]
    client = FakeClient(wrong_sessions, schedule)
    run = tmp_path / "private" / "runs" / f"{RUN_ID}-{missing_boundary}"
    with pytest.raises(
        RuntimeError,
        match="calendar did not span the exact frozen provider period",
    ):
        acquisition.acquire(client, run.name, run)
    assert [call["endpoint"] for call in client.calls] == ["/markets/calendar"]


@pytest.mark.parametrize("failure_kind", ["http_413", "response_too_large"])
def test_first_range_413_or_oversize_falls_back_to_single_session_no_retry(
    tmp_path: Path,
    monkeypatch,
    compact_schedule: tuple[pd.DatetimeIndex, SelectionSchedule],
    failure_kind: str,
) -> None:
    sessions, schedule = compact_schedule
    error: BaseException
    if failure_kind == "http_413":
        error = HttpStatusError("/equities/bars/daily", 413)
        expected_reason = "http_413"
    else:
        error = ResponseTooLarge("synthetic local response cap")
        expected_reason = "local_response_size_cap"
    client = FakeClient(sessions, schedule, first_range_error=error)
    run = tmp_path / "private" / "runs" / RUN_ID

    class StopAfterDiscovery(RuntimeError):
        pass

    monkeypatch.setattr(
        acquisition,
        "_preliminary_rank",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(StopAfterDiscovery()),
    )
    with pytest.raises(StopAfterDiscovery):
        acquisition.acquire(client, RUN_ID, run)

    checkpoint = json.loads(
        (run / "checkpoint" / "acquisition.json").read_text(encoding="utf-8")
    )
    assert checkpoint["rank_method"] == "single_session_no_retry"
    assert checkpoint["rank_fallback_reason"] == expected_reason
    range_calls = [
        call
        for call in client.calls
        if call["endpoint"] == "/equities/bars/daily"
        and "from" in call["parameters"]
        and "code" not in call["parameters"]
    ]
    date_calls = [
        call
        for call in client.calls
        if call["endpoint"] == "/equities/bars/daily"
        and "date" in call["parameters"]
    ]
    assert len(range_calls) == 1
    assert len(date_calls) == 60
    assert all(
        call["maximum_pages"] == 1 and call["maximum_retries"] == 0
        for call in date_calls
    )


def test_checkpoint_resume_skips_fetched_history_and_finishes_pointer_frontier(
    tmp_path: Path,
    monkeypatch,
    compact_schedule: tuple[pd.DatetimeIndex, SelectionSchedule],
) -> None:
    sessions, schedule = compact_schedule
    run = tmp_path / "private" / "runs" / RUN_ID
    ranked = [
        {"code": CODES[0], "liquidity": 2_000_000_000.0, "sector": "0050"},
        {"code": CODES[1], "liquidity": 1_500_000_000.0, "sector": "1050"},
    ]
    monkeypatch.setattr(
        acquisition,
        "_preliminary_rank",
        lambda *_args, **_kwargs: list(ranked),
    )
    monkeypatch.setattr(acquisition, "load_u15_codes", lambda: [])
    monkeypatch.setattr(
        acquisition,
        "build_deletion_manifest",
        lambda *_args, **_kwargs: {"entries": []},
    )

    interrupted = FakeClient(
        sessions,
        schedule,
        fail_history_code=CODES[1],
    )
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        acquisition.acquire(interrupted, RUN_ID, run)

    interrupted_checkpoint = json.loads(
        (run / "checkpoint" / "acquisition.json").read_text(encoding="utf-8")
    )
    assert interrupted_checkpoint["stage"] == "candidate_histories"
    assert interrupted_checkpoint["fetched_candidate_codes"] == [CODES[0]]
    assert interrupted_checkpoint["pointers"] == {"2024": 1}
    assert (run / "normalized" / "bars" / f"{CODES[0]}.json").is_file()
    assert not (run / "normalized" / "bars" / f"{CODES[1]}.json").exists()

    resumed = FakeClient(sessions, schedule)
    result = acquisition.acquire(resumed, RUN_ID, run)
    resumed_history_codes = [
        call["parameters"]["code"]
        for call in resumed.calls
        if call["endpoint"] == "/equities/bars/daily"
        and "code" in call["parameters"]
    ]
    assert resumed_history_codes == [CODES[1]]
    assert result["stage"] == "complete"
    assert result["candidate_histories"] == 2
    completed = json.loads(
        (run / "checkpoint" / "acquisition.json").read_text(encoding="utf-8")
    )
    assert completed["stage"] == "complete"
    assert completed["fetched_candidate_codes"] == list(CODES)
    assert completed["pointers"] == {"2024": 2}
