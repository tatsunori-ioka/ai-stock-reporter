from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

import pytest

from pit_lite.api import (
    ALLOWED_ENDPOINTS,
    HARD_ATTEMPT_LIMIT,
    API_KEY_HEADER,
    ApiError,
    AttemptJournal,
    AttemptLimitExceeded,
    HttpResponse,
    HttpStatusError,
    RateLimiter,
    SafeApiClient,
    UnsafeRequest,
    _retryable,
)


SECRET = "unit-test-secret-sentinel-never-persist"


class SyntheticTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "timeout_seconds": timeout_seconds,
            }
        )
        if not self.responses:
            raise AssertionError("unexpected synthetic transport call")
        return self.responses.pop(0)


def response(
    rows: list[dict[str, Any]] | None = None,
    *,
    status: int = 200,
    pagination_key: str | None = None,
) -> HttpResponse:
    payload: dict[str, Any] = {"data": rows or []}
    if pagination_key is not None:
        payload["pagination_key"] = pagination_key
    return HttpResponse(status=status, body=json.dumps(payload).encode("utf-8"))


def client(
    tmp_path: Path,
    transport: SyntheticTransport,
    *,
    hard_limit: int = HARD_ATTEMPT_LIMIT,
) -> SafeApiClient:
    journal = AttemptJournal(
        tmp_path / "checkpoint" / "attempts.jsonl",
        hard_limit=hard_limit,
    )
    return SafeApiClient(
        SECRET,
        tmp_path,
        transport=transport,
        journal=journal,
        rate_limiter=RateLimiter(0),
        sleeper=lambda _: None,
    )


def test_api_allowlist_and_hard_budget_are_frozen() -> None:
    assert HARD_ATTEMPT_LIMIT == 3000
    assert ALLOWED_ENDPOINTS == {
        "/markets/calendar",
        "/equities/master",
        "/equities/bars/daily",
    }


def test_rate_limiter_keeps_consecutive_dispatches_at_least_one_second_apart() -> None:
    class FakeClock:
        def __init__(self) -> None:
            self.now = 100.0
            self.sleeps: list[float] = []

        def clock(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.sleeps.append(seconds)
            self.now += seconds

    fake = FakeClock()
    limiter = RateLimiter(1.0, clock=fake.clock, sleeper=fake.sleep)
    dispatches: list[float] = []
    limiter.wait()
    dispatches.append(fake.now)
    fake.now += 0.25
    limiter.wait()
    dispatches.append(fake.now)
    fake.now += 0.60
    limiter.wait()
    dispatches.append(fake.now)

    gaps = [
        later - earlier
        for earlier, later in zip(dispatches, dispatches[1:])
    ]
    assert gaps == pytest.approx([1.0, 1.0])
    assert fake.sleeps == pytest.approx([0.75, 0.40])


def test_secret_is_only_in_header_not_url_journal_cache_or_raw_filename(
    tmp_path: Path,
) -> None:
    transport = SyntheticTransport([response([{"Date": "2024-01-01"}])])
    api = client(tmp_path, transport)
    api.get_paginated(
        "/markets/calendar",
        {"from": "20240101", "to": "20240131"},
        request_id="calendar",
        maximum_pages=1,
    )
    assert transport.calls[0]["headers"][API_KEY_HEADER] == SECRET
    assert SECRET not in transport.calls[0]["url"]
    persisted = b"".join(
        path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()
    )
    assert SECRET.encode() not in persisted
    assert all(SECRET not in path.name for path in tmp_path.rglob("*"))
    assert SECRET not in json.dumps(api.sanitized_audit())


def test_unallowlisted_endpoint_is_rejected_before_transport(tmp_path: Path) -> None:
    transport = SyntheticTransport([])
    api = client(tmp_path, transport)
    with pytest.raises(UnsafeRequest):
        api.get_paginated(
            "/listed/info",
            {},
            request_id="forbidden",
            maximum_pages=1,
        )
    assert transport.calls == []
    assert api.journal.used == 0


def test_hard_budget_rejects_attempt_before_transport(tmp_path: Path) -> None:
    transport = SyntheticTransport([response(), response()])
    api = client(tmp_path, transport, hard_limit=1)
    api.get_paginated(
        "/equities/master",
        {"date": "20240401"},
        request_id="first",
        maximum_pages=1,
    )
    with pytest.raises(AttemptLimitExceeded):
        api.get_paginated(
            "/equities/master",
            {"date": "20250401"},
            request_id="second",
            maximum_pages=1,
        )
    assert api.journal.used == 1
    assert len(transport.calls) == 1


def test_attempt_journal_counts_preserved_attempts_on_resume(tmp_path: Path) -> None:
    journal_path = tmp_path / "attempts.jsonl"
    journal = AttemptJournal(journal_path, hard_limit=3)
    journal.consume(
        endpoint="/equities/master",
        request_id="one",
        page_number=1,
        retry_number=0,
    )
    resumed = AttemptJournal(journal_path, hard_limit=3)
    assert resumed.used == 1
    assert resumed.consume(
        endpoint="/equities/master",
        request_id="two",
        page_number=1,
        retry_number=0,
    ) == 2


def test_retry_only_transient_statuses_with_frozen_backoff(tmp_path: Path) -> None:
    transport = SyntheticTransport(
        [
            response(status=429),
            response(status=503),
            response([{"Code": "12340"}]),
        ]
    )
    delays: list[float] = []
    api = client(tmp_path, transport)
    api.sleeper = delays.append
    rows, metadata = api.get_paginated(
        "/equities/master",
        {"date": "20240401"},
        request_id="retry",
        maximum_pages=1,
    )
    assert rows == [{"Code": "12340"}]
    assert metadata["http_statuses"] == [429, 503, 200]
    assert delays == [1.0, 2.0]
    assert api.journal.used == 3
    assert len(transport.calls) == 3


@pytest.mark.parametrize("status", [429, 500, 501, 550, 598, 599])
def test_retry_policy_includes_429_and_entire_500_to_599_range(
    status: int,
) -> None:
    assert _retryable(status) is True


@pytest.mark.parametrize("status", [400, 428, 430, 499, 600])
def test_retry_policy_excludes_other_statuses(status: int) -> None:
    assert _retryable(status) is False


def test_nontransient_status_has_no_retry_and_body_is_suppressed(
    tmp_path: Path,
) -> None:
    body = b'{"message":"provider-secret-detail"}'
    transport = SyntheticTransport([HttpResponse(status=401, body=body), response()])
    api = client(tmp_path, transport)
    with pytest.raises(HttpStatusError) as captured:
        api.get_paginated(
            "/equities/master",
            {},
            request_id="unauthorized",
            maximum_pages=1,
        )
    assert len(transport.calls) == 1
    assert "provider-secret-detail" not in str(captured.value)


def test_transient_status_stops_after_exactly_two_retries(tmp_path: Path) -> None:
    transport = SyntheticTransport(
        [response(status=500), response(status=500), response(status=500), response()]
    )
    api = client(tmp_path, transport)
    with pytest.raises(HttpStatusError):
        api.get_paginated(
            "/equities/master",
            {},
            request_id="server-error",
            maximum_pages=1,
        )
    assert len(transport.calls) == 3
    assert api.journal.used == 3


def test_pagination_is_complete_and_next_key_is_not_applied_to_first_page(
    tmp_path: Path,
) -> None:
    transport = SyntheticTransport(
        [
            response([{"Code": "11110"}], pagination_key="next-2"),
            response([{"Code": "22220"}]),
        ]
    )
    api = client(tmp_path, transport)
    rows, metadata = api.get_paginated(
        "/equities/master",
        {"date": "20240401"},
        request_id="pages",
        maximum_pages=2,
    )
    first = urllib.parse.parse_qs(urllib.parse.urlsplit(transport.calls[0]["url"]).query)
    second = urllib.parse.parse_qs(urllib.parse.urlsplit(transport.calls[1]["url"]).query)
    assert "pagination_key" not in first
    assert second["pagination_key"] == ["next-2"]
    assert rows == [{"Code": "11110"}, {"Code": "22220"}]
    assert metadata["page_count"] == 2
    assert metadata["pagination_complete"] is True


def test_pagination_cycle_fails_closed(tmp_path: Path) -> None:
    transport = SyntheticTransport(
        [
            response([{"Code": "11110"}], pagination_key="same"),
            response([{"Code": "22220"}], pagination_key="same"),
        ]
    )
    api = client(tmp_path, transport)
    with pytest.raises(ApiError, match="cyclic"):
        api.get_paginated(
            "/equities/master",
            {},
            request_id="cycle",
            maximum_pages=3,
        )
    assert len(transport.calls) == 2


def test_pagination_page_cap_fails_closed(tmp_path: Path) -> None:
    transport = SyntheticTransport(
        [response([{"Code": "11110"}], pagination_key="more")]
    )
    api = client(tmp_path, transport)
    with pytest.raises(ApiError, match="page cap"):
        api.get_paginated(
            "/equities/master",
            {},
            request_id="capped",
            maximum_pages=1,
        )
    assert len(transport.calls) == 1


def test_same_request_uses_private_cache_with_zero_new_attempts(tmp_path: Path) -> None:
    transport = SyntheticTransport([response([{"Code": "11110"}])])
    api = client(tmp_path, transport)
    first = api.get_paginated(
        "/equities/master",
        {"date": "20240401"},
        request_id="cached",
        maximum_pages=1,
    )
    second = api.get_paginated(
        "/equities/master",
        {"date": "20240401"},
        request_id="cached",
        maximum_pages=1,
    )
    assert first == second
    assert len(transport.calls) == 1
    assert api.journal.used == 1
    assert api.cache_hits == 1


def test_cache_identity_mismatch_fails_closed_without_network(tmp_path: Path) -> None:
    transport = SyntheticTransport([response()])
    api = client(tmp_path, transport)
    path = api._cache_path("cached", "/equities/master", {"date": "20240401"})
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "request_identity_sha256": "0" * 64,
                "rows": [],
                "metadata": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="identity mismatch"):
        api.get_paginated(
            "/equities/master",
            {"date": "20240401"},
            request_id="cached",
            maximum_pages=1,
        )
    assert transport.calls == []
