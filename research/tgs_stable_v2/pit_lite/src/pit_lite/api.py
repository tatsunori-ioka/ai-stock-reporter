from __future__ import annotations

import hashlib
import fcntl
import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Protocol

from .contract import CONTRACT, canonical_sha256
from .safety import (
    SafetyError,
    atomic_write_bytes,
    atomic_write_json,
    read_json,
)


API_BASE = "https://api.jquants.com/v2"
API_HOST = "api.jquants.com"
API_KEY_ENV = "JQUANTS_API_KEY"
API_KEY_HEADER = "x-api-key"
ALLOWED_ENDPOINTS = frozenset(
    {"/markets/calendar", "/equities/master", "/equities/bars/daily"}
)
HARD_ATTEMPT_LIMIT = 3000
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
RETRY_DELAYS = (1.0, 2.0)
SYSTEM_CA_BUNDLE = Path("/etc/ssl/cert.pem")


class ApiError(RuntimeError):
    """Sanitized API failure."""


class AttemptLimitExceeded(ApiError):
    """Raised before an attempt over the hard gate."""


class ResponseTooLarge(ApiError):
    """Raised without parsing an oversized response."""


class UnsafeRequest(ApiError):
    """Raised for a request outside the fixed allowlist."""


class HttpStatusError(ApiError):
    """Non-success provider status without response-body disclosure."""

    def __init__(self, endpoint: str, status: int) -> None:
        super().__init__(f"HTTP {status} for {endpoint}; response detail suppressed")
        self.endpoint = endpoint
        self.status = status


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes


class Transport(Protocol):
    def get(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(  # type: ignore[override]
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Mapping[str, str],
        newurl: str,
    ) -> None:
        return None


def validate_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != API_HOST:
        raise UnsafeRequest("only the official J-Quants HTTPS host is allowed")
    if parsed.path.removeprefix("/v2") not in ALLOWED_ENDPOINTS:
        raise UnsafeRequest("endpoint is not allowlisted")
    if parsed.username or parsed.password or parsed.fragment:
        raise UnsafeRequest("credentials or fragments in URLs are forbidden")


class UrlLibTransport:
    """TLS-verifying GET transport with redirects and implicit retries disabled."""

    def __init__(self, max_response_bytes: int = MAX_RESPONSE_BYTES) -> None:
        self.max_response_bytes = max_response_bytes
        context = (
            ssl.create_default_context(cafile=str(SYSTEM_CA_BUNDLE))
            if SYSTEM_CA_BUNDLE.is_file()
            else ssl.create_default_context()
        )
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context),
            _NoRedirect(),
        )

    def get(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        validate_url(url)
        request = urllib.request.Request(url, headers=dict(headers), method="GET")
        try:
            with self._opener.open(request, timeout=timeout_seconds) as response:
                body = response.read(self.max_response_bytes + 1)
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            body = exc.read(self.max_response_bytes + 1)
            status = int(exc.code)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ApiError("network or TLS transport failed; detail suppressed") from exc
        if len(body) > self.max_response_bytes:
            raise ResponseTooLarge("response exceeded the 16 MiB safety limit")
        return HttpResponse(status=status, body=body)


def filevault_is_active() -> bool:
    try:
        result = subprocess.run(
            ["/usr/bin/fdesetup", "isactive"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


class AttemptJournal:
    """Durable pre-dispatch accounting across crashes and resumes."""

    def __init__(self, path: Path, *, hard_limit: int = HARD_ATTEMPT_LIMIT) -> None:
        self.path = path
        self.hard_limit = hard_limit
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.path.exists():
            atomic_write_bytes(self.path, b"")
        self.used = sum(1 for line in self.path.read_text(encoding="utf-8").splitlines() if line)
        if self.used > self.hard_limit:
            raise SafetyError("attempt journal already exceeds the hard limit")

    def consume(
        self,
        *,
        endpoint: str,
        request_id: str,
        page_number: int,
        retry_number: int,
    ) -> int:
        descriptor = os.open(self.path, os.O_RDWR | os.O_APPEND)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            os.lseek(descriptor, 0, os.SEEK_SET)
            current = sum(
                1
                for line in os.read(descriptor, os.path.getsize(self.path)).splitlines()
                if line
            )
            if current >= self.hard_limit:
                raise AttemptLimitExceeded(
                    f"request budget exhausted at {current}/{self.hard_limit}"
                )
            self.used = current + 1
            entry = json.dumps(
                {
                    "attempt": self.used,
                    "endpoint": endpoint,
                    "page_number": page_number,
                    "request_id": request_id,
                    "retry_number": retry_number,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
            os.write(descriptor, entry)
            os.fsync(descriptor)
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
        return self.used


class RateLimiter:
    def __init__(
        self,
        minimum_interval_seconds: float = 1.0,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.minimum_interval_seconds = max(0.0, minimum_interval_seconds)
        self.clock = clock
        self.sleeper = sleeper
        self.last_dispatch: float | None = None

    def wait(self) -> None:
        now = self.clock()
        if self.last_dispatch is not None:
            remaining = self.minimum_interval_seconds - (now - self.last_dispatch)
            if remaining > 0:
                self.sleeper(remaining)
        self.last_dispatch = self.clock()


def _slug(value: str) -> str:
    result = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value)
    return result[:160]


def _retryable(status: int) -> bool:
    return status == 429 or 500 <= status <= 599


class SafeApiClient:
    """Single-threaded, explicitly retried, private-cache J-Quants client."""

    def __init__(
        self,
        api_key: str,
        run_directory: Path,
        *,
        transport: Transport | None = None,
        journal: AttemptJournal | None = None,
        rate_limiter: RateLimiter | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key:
            raise ValueError("API key is required")
        self._api_key = api_key
        self.run_directory = run_directory
        self.raw_directory = run_directory / "raw"
        self.cache_directory = run_directory / "normalized" / "request_cache"
        self.transport = transport or UrlLibTransport()
        self.journal = journal or AttemptJournal(
            run_directory / "checkpoint" / "attempts.jsonl"
        )
        self.rate_limiter = rate_limiter or RateLimiter(1.0)
        self.sleeper = sleeper
        self.timeout_seconds = timeout_seconds
        self.response_journal = run_directory / "checkpoint" / "responses.jsonl"
        if not self.response_journal.exists():
            atomic_write_bytes(self.response_journal, b"")
        self.cache_hits = 0

    def _record_response(self, endpoint: str, status: int) -> None:
        entry = json.dumps(
            {"endpoint": endpoint, "status": status},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        descriptor = os.open(self.response_journal, os.O_WRONLY | os.O_APPEND)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            os.write(descriptor, entry)
            os.fsync(descriptor)
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _url(self, endpoint: str, query: Mapping[str, str]) -> str:
        if endpoint not in ALLOWED_ENDPOINTS:
            raise UnsafeRequest("endpoint is not allowlisted")
        url = f"{API_BASE}{endpoint}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        validate_url(url)
        return url

    def _raw_path(
        self,
        attempt: int,
        request_id: str,
        page_number: int,
        retry_number: int,
    ) -> Path:
        return self.raw_directory / (
            f"{attempt:04d}-{_slug(request_id)}-p{page_number}-r{retry_number}.json"
        )

    def _cache_path(self, request_id: str, endpoint: str, parameters: Mapping[str, str]) -> Path:
        identity = canonical_sha256(
            {"request_id": request_id, "endpoint": endpoint, "parameters": parameters}
        )
        return self.cache_directory / f"{_slug(request_id)}-{identity[:16]}.json"

    def get_paginated(
        self,
        endpoint: str,
        parameters: Mapping[str, str],
        *,
        request_id: str,
        maximum_pages: int,
        maximum_retries: int = 2,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if maximum_pages < 1:
            raise ValueError("maximum_pages must be positive")
        if maximum_retries < 0 or maximum_retries > len(RETRY_DELAYS):
            raise ValueError("maximum_retries must be between zero and two")
        cache_path = self._cache_path(request_id, endpoint, parameters)
        if cache_path.is_file():
            cached = read_json(cache_path)
            expected_identity = canonical_sha256(
                {"request_id": request_id, "endpoint": endpoint, "parameters": parameters}
            )
            if cached.get("request_identity_sha256") != expected_identity:
                raise SafetyError("private request cache identity mismatch")
            self.cache_hits += 1
            return list(cached["rows"]), dict(cached["metadata"])

        all_rows: list[dict[str, Any]] = []
        page_hashes: list[str] = []
        statuses: list[int] = []
        query: MutableMapping[str, str] = dict(parameters)
        pagination_key: str | None = None
        seen_keys: set[str] = set()
        response_bytes = 0

        for page_number in range(1, maximum_pages + 1):
            if pagination_key is not None:
                query["pagination_key"] = pagination_key
            url = self._url(endpoint, query)
            response: HttpResponse | None = None
            for retry_number in range(0, maximum_retries + 1):
                attempt = self.journal.consume(
                    endpoint=endpoint,
                    request_id=request_id,
                    page_number=page_number,
                    retry_number=retry_number,
                )
                self.rate_limiter.wait()
                response = self.transport.get(
                    url,
                    {API_KEY_HEADER: self._api_key, "Accept": "application/json"},
                    self.timeout_seconds,
                )
                self._record_response(endpoint, response.status)
                atomic_write_bytes(
                    self._raw_path(attempt, request_id, page_number, retry_number),
                    response.body,
                )
                statuses.append(response.status)
                if response.status == 200:
                    break
                if not _retryable(response.status) or retry_number >= maximum_retries:
                    raise HttpStatusError(endpoint, response.status)
                self.sleeper(RETRY_DELAYS[retry_number])

            if response is None or response.status != 200:
                raise ApiError("request did not produce a successful response")
            response_bytes += len(response.body)
            page_hashes.append(hashlib.sha256(response.body).hexdigest())
            try:
                payload = json.loads(response.body)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ApiError("provider returned invalid JSON") from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise ApiError("provider response schema mismatch")
            if not all(isinstance(row, dict) for row in payload["data"]):
                raise ApiError("provider row schema mismatch")
            all_rows.extend(payload["data"])
            next_key = payload.get("pagination_key")
            if next_key in (None, ""):
                pagination_key = None
                break
            if not isinstance(next_key, str) or next_key in seen_keys:
                raise ApiError("unsafe or cyclic pagination key")
            seen_keys.add(next_key)
            pagination_key = next_key
        else:
            if pagination_key is not None:
                raise ApiError("pagination exceeded the frozen page cap")

        metadata = {
            "endpoint": endpoint,
            "page_count": len(page_hashes),
            "response_bytes": response_bytes,
            "row_count": len(all_rows),
            "http_statuses": statuses,
            "logical_response_sha256": canonical_sha256(page_hashes),
            "pagination_complete": pagination_key is None,
        }
        cache_payload = {
            "request_identity_sha256": canonical_sha256(
                {"request_id": request_id, "endpoint": endpoint, "parameters": parameters}
            ),
            "metadata": metadata,
            "rows": all_rows,
        }
        atomic_write_json(cache_path, cache_payload)
        return all_rows, metadata

    def sanitized_audit(self) -> dict[str, Any]:
        endpoint_attempts = {endpoint: 0 for endpoint in ALLOWED_ENDPOINTS}
        for line in self.journal.path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            endpoint = str(json.loads(line)["endpoint"])
            endpoint_attempts[endpoint] = endpoint_attempts.get(endpoint, 0) + 1
        http_status_counts: dict[str, int] = {}
        for line in self.response_journal.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            status = str(json.loads(line)["status"])
            http_status_counts[status] = http_status_counts.get(status, 0) + 1
        return {
            "attempts_used": self.journal.used,
            "hard_attempt_limit": self.journal.hard_limit,
            "endpoint_attempt_counts": dict(sorted(endpoint_attempts.items())),
            "http_status_counts": dict(sorted(http_status_counts.items())),
            "cache_hits": self.cache_hits,
            "single_threaded": True,
            "implicit_retries": 0,
            "maximum_retries_per_page": len(RETRY_DELAYS),
            "credential_recorded": False,
        }


@dataclass(frozen=True)
class AcquisitionPlan:
    base_commit: str
    provider_earliest_date: str
    frozen_end_date: str
    selection_start_year: int
    selection_end_year: int
    rank_window_sessions: int
    rank_sessions_per_chunk: int
    rank_page_cap: int
    candidate_frontier_cap: int
    candidate_page_cap: int
    u15_code_count: int
    expected_attempts: int
    planned_worst_case_attempts: int
    hard_attempt_limit: int

    @property
    def sha256(self) -> str:
        return canonical_sha256(asdict(self))


def frozen_acquisition_plan() -> AcquisitionPlan:
    api = CONTRACT["api"]
    period = CONTRACT["period"]
    return AcquisitionPlan(
        base_commit=str(CONTRACT["base_commit"]),
        provider_earliest_date=str(period["provider_earliest_date"]),
        frozen_end_date=str(period["frozen_end_date"]),
        selection_start_year=min(period["selection_years"]),
        selection_end_year=max(period["selection_years"]),
        rank_window_sessions=60,
        rank_sessions_per_chunk=int(api["rank_window_sessions_per_chunk"]),
        rank_page_cap=int(api["rank_window_page_cap"]),
        candidate_frontier_cap=int(api["candidate_frontier_cap"]),
        candidate_page_cap=int(api["candidate_history_page_cap"]),
        u15_code_count=15,
        expected_attempts=int(api["estimated_expected_attempts"]),
        planned_worst_case_attempts=int(api["planned_worst_case_attempts"]),
        hard_attempt_limit=int(api["hard_attempt_limit"]),
    )
