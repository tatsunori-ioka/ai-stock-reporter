#!/usr/bin/env python3
"""Bounded, read-only J-Quants API V2 capability probe.

The default invocation is a zero-network dry run. Live access requires
``--live`` plus an API key in ``JQUANTS_API_KEY``. Raw response bodies exist
only inside a temporary directory outside the repository and are deleted when
the probe exits. Committed outputs contain metadata and aggregates only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Protocol, Sequence


API_BASE = "https://api.jquants.com/v2"
API_HOST = "api.jquants.com"
API_VERSION = "v2"
API_KEY_ENV = "JQUANTS_API_KEY"
API_KEY_HEADER = "x-api-key"
MAX_API_REQUESTS = 30
MAX_PAGES_PER_PROBE = 3
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MIN_INTERVAL_SECONDS = 1.0
SYSTEM_CA_BUNDLE = Path("/etc/ssl/cert.pem")
SCHEMA_VERSION = "1.0"
BASE_COMMIT = "52ead3fe27c67da60d8eede4bc38fd1b4311f8ce"
ALLOWED_ENDPOINTS = frozenset({"/equities/master", "/equities/bars/daily"})

DATA_REALITY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_DIR = DATA_REALITY_ROOT / "results"
REPOSITORY_ROOT = DATA_REALITY_ROOT.parents[2]

MASTER_REQUIRED_FIELDS = ("Date", "Code", "S17", "S33", "Mkt")
BAR_REQUIRED_FIELDS = (
    "Date",
    "Code",
    "O",
    "H",
    "L",
    "C",
    "Vo",
    "Va",
    "AdjFactor",
    "AdjO",
    "AdjH",
    "AdjL",
    "AdjC",
    "AdjVo",
)

MASTER_PROBES: tuple[dict[str, Any], ...] = (
    {"probe_id": "master_2010_04_01", "parameters": {"date": "20100401"}},
    {"probe_id": "master_2015_04_01", "parameters": {"date": "20150401"}},
    {"probe_id": "master_2020_04_01", "parameters": {"date": "20200401"}},
    {"probe_id": "master_2025_04_01", "parameters": {"date": "20250401"}},
    {"probe_id": "master_latest", "parameters": {}},
)

# Corporate-action seeds come from the cited official JPX notices.
BAR_PROBES: tuple[dict[str, Any], ...] = (
    {
        "probe_id": "bars_split_8697",
        "parameters": {
            "code": "86970",
            "from": "20240924",
            "to": "20241004",
        },
        "purpose": "official_split_example",
        "action_type": "split",
        "official_effective_date": "2024-10-01",
        "official_ratio": "1:2",
        "expected_adjustment_factor": 0.5,
        "official_source": (
            "https://www.jpx.co.jp/corporate/news/news-releases/0063/"
            "mklp770000006msc-att/20240513_J_1.pdf"
        ),
    },
    {
        "probe_id": "bars_split_7011",
        "parameters": {
            "code": "70110",
            "from": "20240325",
            "to": "20240405",
        },
        "purpose": "official_split_example",
        "action_type": "split",
        "official_effective_date": "2024-04-01",
        "official_ratio": "1:10",
        "expected_adjustment_factor": 0.1,
        "official_source": (
            "https://www.jpx.co.jp/english/news/2020/20240314-01.html"
        ),
    },
    {
        "probe_id": "bars_reverse_split_8411",
        "parameters": {
            "code": "84110",
            "from": "20200923",
            "to": "20201007",
        },
        "purpose": "official_reverse_split_example",
        "action_type": "reverse_split",
        "official_effective_date": "2020-10-01",
        "official_ratio": "10:1",
        "expected_adjustment_factor": 10.0,
        "official_source": (
            "https://www.jpx.co.jp/english/news/2020/20200915-03.html"
        ),
    },
    {
        "probe_id": "bars_delisted_7829",
        "parameters": {
            "code": "78290",
            "from": "20240617",
            "to": "20240628",
        },
        "purpose": "official_delisted_example",
        "official_delisting_date": "2024-06-27",
        "official_source": (
            "https://www.jpx.co.jp/news/1023/20240626-11.html"
        ),
    },
)

OFFICIAL_SOURCES: tuple[dict[str, str], ...] = (
    {
        "id": "personal_eq_master",
        "url": "https://jpx-jquants.com/ja/spec/eq-master",
    },
    {
        "id": "personal_daily_bars",
        "url": "https://jpx-jquants.com/ja/spec/eq-bars-daily",
    },
    {
        "id": "personal_adjustment_logic",
        "url": "https://jpx-jquants.com/ja/spec/eq-bars-daily/adj",
    },
    {
        "id": "personal_data_periods",
        "url": "https://jpx-jquants.com/ja/spec/data-spec",
    },
    {
        "id": "personal_rate_limits",
        "url": "https://jpx-jquants.com/ja/spec/rate-limits",
    },
    {
        "id": "personal_terms",
        "url": "https://jpx-jquants.com/en/termsofservice",
    },
    {
        "id": "personal_terms_japanese_authoritative_text",
        "url": "https://jpx-jquants.com/ja/termsofservice",
    },
    {
        "id": "personal_faq",
        "url": "https://jpx-jquants.com/",
    },
    {
        "id": "jpx_service_overview",
        "url": (
            "https://www.jpx.co.jp/markets/other-data-services/"
            "j-quants-api/index.html"
        ),
    },
    {
        "id": "pro_listed_issue_information",
        "url": "https://pro.jpx-jquants.com/datasets/4",
    },
    {
        "id": "pro_stock_prices",
        "url": "https://pro.jpx-jquants.com/datasets/9",
    },
    {
        "id": "pro_corporate_actions",
        "url": "https://pro.jpx-jquants.com/datasets/14",
    },
    {
        "id": "pro_listed_shares_flash",
        "url": "https://pro.jpx-jquants.com/datasets/16",
    },
    {
        "id": "pro_listed_shares_corporate_action_factors",
        "url": "https://pro.jpx-jquants.com/datasets/17",
    },
    {
        "id": "jpx_pro_2026_dataset_announcement",
        "url": (
            "https://www.jpx.co.jp/english/corporate/news/"
            "news-releases/6020/20260120-01.html"
        ),
    },
    {
        "id": "pro_listed_shares_flash_schema",
        "url": (
            "https://jpx.gitbook.io/j-quants-pro-ja/"
            "api-reference/listed_shares"
        ),
    },
    {
        "id": "pro_listed_shares_change_schema",
        "url": (
            "https://jpx.gitbook.io/j-quants-pro-ja/"
            "api-reference/listed_shares_change"
        ),
    },
    {
        "id": "pro_delisting_schema",
        "url": (
            "https://jpx.gitbook.io/j-quants-pro-ja/api-reference/"
            "corporate_action/delisting"
        ),
    },
    {
        "id": "pro_stock_detail_change_schema",
        "url": (
            "https://jpx.gitbook.io/j-quants-pro-ja/api-reference/"
            "corporate_action/change_of_stock_detail"
        ),
    },
    {
        "id": "jpx_delisting_notice_7829",
        "url": "https://www.jpx.co.jp/news/1023/20240626-11.html",
    },
)


class ProbeError(RuntimeError):
    """Base class for intentionally sanitized probe failures."""


class RequestLimitExceeded(ProbeError):
    """Raised before a request that would exceed the hard audit budget."""


class ResponseTooLarge(ProbeError):
    """Raised when a response exceeds the bounded probe size."""


class UnsafeRequest(ProbeError):
    """Raised for a non-allowlisted host, scheme, or endpoint."""


class OutputPathError(ProbeError):
    """Raised when generated output would escape the research results folder."""


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
    ) -> HttpResponse:
        """Perform one GET without retries."""


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


class UrlLibTransport:
    """Single-attempt HTTPS transport with redirects disabled."""

    def __init__(self, max_response_bytes: int = MAX_RESPONSE_BYTES) -> None:
        self.max_response_bytes = max_response_bytes
        ssl_context = (
            ssl.create_default_context(cafile=str(SYSTEM_CA_BUNDLE))
            if SYSTEM_CA_BUNDLE.is_file()
            else ssl.create_default_context()
        )
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl_context),
            _NoRedirect(),
        )

    def get(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        validate_url(url)
        request = urllib.request.Request(
            url,
            headers=dict(headers),
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=timeout_seconds) as response:
                body = response.read(self.max_response_bytes + 1)
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            body = exc.read(self.max_response_bytes + 1)
            status = int(exc.code)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProbeError(
                "network transport failed before an HTTP response"
            ) from exc
        if len(body) > self.max_response_bytes:
            raise ResponseTooLarge("response exceeded the safe byte limit")
        return HttpResponse(status=status, body=body)


class RequestBudget:
    """Counts every HTTP attempt before dispatch."""

    def __init__(
        self,
        limit: int = MAX_API_REQUESTS,
        *,
        initial_used: int = 0,
    ) -> None:
        if limit < 0 or limit > MAX_API_REQUESTS:
            raise ValueError(f"request limit must be between 0 and {MAX_API_REQUESTS}")
        if initial_used < 0 or initial_used > limit:
            raise ValueError("initial request count must be within the request limit")
        self.limit = limit
        self.used = initial_used
        self.initial_used = initial_used

    def consume(self) -> int:
        if self.used >= self.limit:
            raise RequestLimitExceeded(
                f"request budget exhausted at {self.used}/{self.limit}"
            )
        self.used += 1
        return self.used


class RateLimiter:
    """Conservative single-thread request spacing."""

    def __init__(
        self,
        min_interval_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self._clock = clock
        self._sleeper = sleeper
        self._last_dispatch: float | None = None

    def wait(self) -> None:
        now = self._clock()
        if self._last_dispatch is not None:
            remaining = self.min_interval_seconds - (now - self._last_dispatch)
            if remaining > 0:
                self._sleeper(remaining)
                now = self._clock()
        self._last_dispatch = now


def validate_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != API_HOST:
        raise UnsafeRequest("only the official J-Quants HTTPS host is allowed")
    if parsed.path.removeprefix("/v2") not in ALLOWED_ENDPOINTS:
        raise UnsafeRequest("endpoint is not in the read-only audit allowlist")
    if parsed.username or parsed.password or parsed.fragment:
        raise UnsafeRequest("credentials and fragments are forbidden in request URLs")


def validate_temp_root(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    allowed_roots = {
        Path("/tmp").resolve(),
        Path(tempfile.gettempdir()).resolve(),
    }
    if not any(
        resolved == allowed or allowed in resolved.parents
        for allowed in allowed_roots
    ):
        raise OutputPathError(
            "raw response temp root must be inside a system temporary directory"
        )
    repository = REPOSITORY_ROOT.resolve()
    if resolved == repository or repository in resolved.parents:
        raise OutputPathError("raw response temp root cannot be inside the repository")
    if not resolved.is_dir():
        raise OutputPathError("raw response temp root must already be a directory")
    return resolved


def _status_from_http(status: int) -> str:
    if status == 200:
        return "ok"
    if status == 401:
        return "auth_failed"
    if status == 403:
        return "entitlement_denied"
    if status == 429:
        return "rate_limited"
    if 400 <= status < 500:
        return "request_rejected"
    if 500 <= status:
        return "provider_error"
    if 300 <= status < 400:
        return "redirect_rejected"
    return "unexpected_http_status"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _safe_slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)


class SafeApiClient:
    """Minimal client that exposes no implicit retry or parallelism."""

    def __init__(
        self,
        api_key: str,
        *,
        transport: Transport,
        budget: RequestBudget,
        rate_limiter: RateLimiter,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not api_key:
            raise ValueError("API key is required")
        self._api_key = api_key
        self._transport = transport
        self._budget = budget
        self._rate_limiter = rate_limiter
        self._timeout_seconds = timeout_seconds

    def get_paginated(
        self,
        endpoint: str,
        parameters: Mapping[str, str],
        *,
        raw_directory: Path,
        probe_id: str,
        max_pages: int = MAX_PAGES_PER_PROBE,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if endpoint not in ALLOWED_ENDPOINTS:
            raise UnsafeRequest("endpoint is not in the read-only audit allowlist")
        if max_pages < 1:
            raise ValueError("max_pages must be positive")

        rows: list[dict[str, Any]] = []
        request_metadata: list[dict[str, Any]] = []
        pagination_key: str | None = None
        seen_pagination_keys: set[str] = set()
        logical_hash = hashlib.sha256()
        final_status = "ok"
        pagination_complete = False

        for page_number in range(1, max_pages + 1):
            query: MutableMapping[str, str] = dict(parameters)
            if pagination_key is not None:
                query["pagination_key"] = pagination_key
            url = f"{API_BASE}{endpoint}"
            if query:
                url = f"{url}?{urllib.parse.urlencode(query)}"
            validate_url(url)

            request_number = self._budget.consume()
            self._rate_limiter.wait()
            response = self._transport.get(
                url,
                {API_KEY_HEADER: self._api_key, "Accept": "application/json"},
                self._timeout_seconds,
            )
            response_hash = _sha256_bytes(response.body)
            logical_hash.update(response.body)
            raw_path = raw_directory / (
                f"{request_number:02d}-{_safe_slug(probe_id)}-p{page_number}.json"
            )
            raw_path.write_bytes(response.body)
            request_metadata.append(
                {
                    "request_number": request_number,
                    "page_number": page_number,
                    "http_status": response.status,
                    "response_bytes": len(response.body),
                    "response_sha256": response_hash,
                }
            )

            http_status = _status_from_http(response.status)
            if http_status != "ok":
                final_status = http_status
                break
            try:
                payload = json.loads(response.body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                final_status = "invalid_json"
                break
            if not isinstance(payload, dict) or not isinstance(
                payload.get("data"), list
            ):
                final_status = "schema_mismatch"
                break
            page_rows = payload["data"]
            if not all(isinstance(row, dict) for row in page_rows):
                final_status = "schema_mismatch"
                break
            rows.extend(page_rows)

            next_key = payload.get("pagination_key")
            if next_key in (None, ""):
                pagination_complete = True
                break
            if not isinstance(next_key, str):
                final_status = "schema_mismatch"
                break
            if next_key in seen_pagination_keys:
                final_status = "pagination_cycle"
                break
            seen_pagination_keys.add(next_key)
            pagination_key = next_key
        else:
            final_status = "pagination_truncated"

        metadata = {
            "status": final_status,
            "request_count": len(request_metadata),
            "page_count": len(request_metadata),
            "requests": request_metadata,
            "response_bytes": sum(
                item["response_bytes"] for item in request_metadata
            ),
            "response_sha256": logical_hash.hexdigest(),
            "pagination_complete": pagination_complete,
        }
        return rows, metadata


def _null_counts(rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> dict[str, int]:
    return {
        field: sum(row.get(field) is None for row in rows)
        for field in fields
    }


def _date_bounds(rows: Sequence[Mapping[str, Any]]) -> tuple[str | None, str | None]:
    values = sorted(
        str(row["Date"])
        for row in rows
        if row.get("Date") not in (None, "")
    )
    if not values:
        return None, None
    return values[0], values[-1]


def _summarize_rows(
    rows: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any],
    *,
    probe_id: str,
    endpoint: str,
    parameters: Mapping[str, str],
    required_fields: Sequence[str],
) -> dict[str, Any]:
    fields = sorted({str(field) for row in rows for field in row})
    missing_required = sorted(set(required_fields) - set(fields))
    all_null_required = sorted(
        field
        for field in required_fields
        if field in fields and all(row.get(field) is None for row in rows)
    )
    min_date, max_date = _date_bounds(rows)
    status = str(metadata["status"])
    if status == "ok" and not rows:
        status = "empty_sample"
    if status == "ok" and (missing_required or all_null_required):
        status = "schema_mismatch"
    result = {
        "probe_id": probe_id,
        "endpoint": endpoint,
        "parameters": dict(parameters),
        "status": status,
        "row_count": len(rows),
        "fields": fields,
        "missing_required_fields": missing_required,
        "all_null_required_fields": all_null_required,
        "null_counts": _null_counts(rows, fields),
        "min_date": min_date,
        "max_date": max_date,
        "request_count": metadata["request_count"],
        "page_count": metadata["page_count"],
        "response_bytes": metadata["response_bytes"],
        "response_sha256": metadata["response_sha256"],
        "http_statuses": [
            item["http_status"] for item in metadata["requests"]
        ],
        "pagination_complete": metadata["pagination_complete"],
    }
    if "Code" in fields:
        result["code_set_sha256"] = _canonical_sha256(
            sorted(
                str(row["Code"])
                for row in rows
                if row.get("Code") not in (None, "")
            )
        )
    return result


def _as_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_metric(value: float | None) -> float | None:
    return None if value is None else round(value, 8)


def _corporate_action_metrics(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_adjustment_factor: float | None = None,
) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: str(row.get("Date", "")))
    factor_values = [
        value
        for value in (_as_number(row.get("AdjFactor")) for row in ordered)
        if value is not None
    ]
    non_one_indexes = [
        index
        for index, row in enumerate(ordered)
        if (
            (factor := _as_number(row.get("AdjFactor"))) is not None
            and abs(factor - 1.0) > 1e-12
        )
    ]
    boundary_checks: list[dict[str, Any]] = []
    for index in non_one_indexes[:3]:
        if index == 0:
            continue
        previous = ordered[index - 1]
        current = ordered[index]
        previous_close = _as_number(previous.get("C"))
        current_open = _as_number(current.get("O"))
        previous_adj_close = _as_number(previous.get("AdjC"))
        current_adj_open = _as_number(current.get("AdjO"))
        factor = _as_number(current.get("AdjFactor"))
        raw_gap = (
            current_open / previous_close
            if current_open is not None and previous_close not in (None, 0)
            else None
        )
        adjusted_gap = (
            current_adj_open / previous_adj_close
            if current_adj_open is not None
            and previous_adj_close not in (None, 0)
            else None
        )
        normalized_gap = (
            raw_gap / factor
            if raw_gap is not None and factor not in (None, 0)
            else None
        )
        consistent = (
            normalized_gap is not None
            and adjusted_gap is not None
            and 0.75 <= normalized_gap <= 1.25
            and 0.75 <= adjusted_gap <= 1.25
        )
        boundary_checks.append(
            {
                "adjustment_factor": _round_metric(factor),
                "raw_gap_ratio": _round_metric(raw_gap),
                "factor_normalized_gap_ratio": _round_metric(normalized_gap),
                "adjusted_gap_ratio": _round_metric(adjusted_gap),
                "continuity_within_25_percent": consistent,
            }
        )
    distinct_factors = sorted(set(factor_values))
    official_factor_match = (
        None
        if expected_adjustment_factor is None
        else any(
            abs(value - expected_adjustment_factor) <= 1e-12
            for value in factor_values
        )
    )
    return {
        "adjustment_factor_observation_count": len(factor_values),
        "adjustment_factor_non_one_count": len(non_one_indexes),
        "adjustment_factor_distinct_count": len(distinct_factors),
        "adjustment_factor_min": (
            _round_metric(min(factor_values)) if factor_values else None
        ),
        "adjustment_factor_max": (
            _round_metric(max(factor_values)) if factor_values else None
        ),
        "boundary_checks": boundary_checks,
        "all_observed_boundaries_consistent": bool(boundary_checks)
        and all(item["continuity_within_25_percent"] for item in boundary_checks),
        "official_factor_match": official_factor_match,
    }


def _capability(
    capability_id: str,
    status: str,
    *,
    critical: bool,
    evidence: Sequence[str],
    note: str,
) -> dict[str, Any]:
    return {
        "id": capability_id,
        "status": status,
        "critical_for_formal_u50_u100": critical,
        "evidence": list(evidence),
        "note": note,
    }


def build_capability_matrix(summary: Mapping[str, Any]) -> dict[str, Any]:
    master = summary["listed_issue_master"]["probes"]
    bars = summary["daily_bars"]["probes"]
    master_ok = all(item["status"] == "ok" for item in master)
    historical_master_ok = all(
        item["status"] == "ok"
        and item.get("requested_snapshot_date_match") is True
        for item in master
        if item["parameters"]
    )
    master_fields = set().union(*(set(item["fields"]) for item in master))
    bar_ok = all(item["status"] == "ok" for item in bars)
    bar_fields = set().union(*(set(item["fields"]) for item in bars))
    delisted_verified = bool(
        summary["delisted_issue_example"]["historical_presence_verified"]
    )
    corporate_action_probes = [
        item for item in bars if "corporate_action_metrics" in item
    ]
    adjustment_verified = (
        len(corporate_action_probes) == 3
        and all(
            item["status"] == "ok"
            and item["pagination_complete"] is True
            and item["corporate_action_metrics"][
                "adjustment_factor_non_one_count"
            ]
            > 0
            and item["corporate_action_metrics"][
                "all_observed_boundaries_consistent"
            ]
            is True
            and item["corporate_action_metrics"]["official_factor_match"] is True
            for item in corporate_action_probes
        )
    )

    capabilities = [
        _capability(
            "point_in_time_active_issue_master",
            "AVAILABLE" if historical_master_ok else "PREMIUM_UNKNOWN",
            critical=True,
            evidence=["live_api:master_historical", "official:personal_eq_master"],
            note=(
                "Date-scoped snapshots were returned; the provider maps "
                "non-business dates to the next business-day snapshot."
            ),
        ),
        _capability(
            "delisted_issue_inclusion",
            "PARTIAL" if delisted_verified else "PREMIUM_UNKNOWN",
            critical=True,
            evidence=[
                "live_api:delisted_7829",
                "official:jpx_delisting_notice_7829",
            ],
            note=(
                "One code from an official JPX delisting notice was present "
                "in a pre-delisting master and absent from the latest master. "
                "This bounded example does not prove complete population coverage."
            ),
        ),
        _capability(
            "listing_date",
            "PARTIAL" if master_ok else "PREMIUM_UNKNOWN",
            critical=True,
            evidence=["live_api:master_fields", "official:personal_eq_master"],
            note=(
                "No listing-date field is exposed. A first-presence boundary "
                "could be derived from dense dated snapshots from 2008 onward, "
                "but that acquisition and boundary method were not verified."
            ),
        ),
        _capability(
            "delisting_date",
            "PARTIAL" if master_ok else "PREMIUM_UNKNOWN",
            critical=True,
            evidence=["live_api:master_fields", "official:personal_eq_master"],
            note=(
                "No delisting-date field is exposed. A last-presence boundary "
                "could be derived from dense dated snapshots, but completeness "
                "and exact effective-date semantics were not verified."
            ),
        ),
        _capability(
            "five_year_listing_history_eligibility",
            "PARTIAL" if master_ok else "PREMIUM_UNKNOWN",
            critical=True,
            evidence=[
                "live_api:master_historical",
                "official:personal_eq_master",
            ],
            note=(
                "The frozen eligibility rule needs a reliable five-year listed "
                "history. No listing-date field exists, and the dense "
                "first-presence boundary method has not been verified."
            ),
        ),
        _capability(
            "historical_market_classification",
            (
                "AVAILABLE"
                if historical_master_ok and "Mkt" in master_fields
                else "PREMIUM_UNKNOWN"
            ),
            critical=True,
            evidence=["live_api:master_fields", "official:personal_eq_master"],
            note="Market code/name are effective-date snapshot attributes.",
        ),
        _capability(
            "historical_sector_classification",
            (
                "AVAILABLE"
                if historical_master_ok
                and {"S17", "S33"}.issubset(master_fields)
                else "PREMIUM_UNKNOWN"
            ),
            critical=True,
            evidence=["live_api:master_fields", "official:personal_eq_master"],
            note="17- and 33-sector values are effective-date snapshot attributes.",
        ),
        _capability(
            "security_product_category",
            "PARTIAL" if historical_master_ok and "ProdCat" in master_fields
            else "PREMIUM_UNKNOWN",
            critical=True,
            evidence=["live_api:master_fields", "official:personal_eq_master"],
            note=(
                "ProdCat was returned, but the documented domestic-stock "
                "category does not by itself prove ordinary/common share class."
            ),
        ),
        _capability(
            "historical_market_regime_mapping",
            "PARTIAL" if historical_master_ok and "Mkt" in master_fields
            else "PREMIUM_UNKNOWN",
            critical=True,
            evidence=["live_api:master_fields", "official:personal_eq_master"],
            note=(
                "Historical market codes are present, but a frozen mapping "
                "across First/Second Section, Mothers, JASDAQ, and the later "
                "Prime/Standard/Growth regime has not been specified."
            ),
        ),
        _capability(
            "trading_unit",
            (
                "NOT_AVAILABLE"
                if master_ok
                and not {"TrUnit", "TradingUnit", "Unit"}.intersection(master_fields)
                else "PREMIUM_UNKNOWN"
            ),
            critical=False,
            evidence=["live_api:master_fields", "official:personal_eq_master"],
            note="The personal V2 master exposes no trading-unit field.",
        ),
        _capability(
            "ticker_lineage_or_stable_security_id",
            (
                "NOT_AVAILABLE"
                if master_ok
                and not {
                    "CodeBeforeChange",
                    "PreviousCode",
                    "ISIN",
                    "SecurityId",
                }.intersection(master_fields)
                else "PREMIUM_UNKNOWN"
            ),
            critical=True,
            evidence=[
                "live_api:master_fields",
                "official:pro_stock_detail_change_schema",
            ],
            note=(
                "The personal V2 master has no former-code mapping or permanent "
                "security identifier. Separate Pro corporate-action data exposes "
                "CodeBeforeChange but is not part of personal Premium."
            ),
        ),
        _capability(
            "historical_corporate_group_mapping",
            "NOT_AVAILABLE",
            critical=True,
            evidence=[
                "live_api:master_fields",
                "local:frozen_u50_u100_proposals",
            ],
            note=(
                "The frozen proposals require point-in-time corporate-group "
                "concentration controls. The personal V2 master has no group "
                "identifier or dated group mapping."
            ),
        ),
        _capability(
            "special_treatment_or_untradeable_status",
            "NOT_AVAILABLE",
            critical=True,
            evidence=[
                "live_api:master_fields",
                "local:frozen_u50_u100_proposals",
            ],
            note=(
                "The frozen eligibility contract excludes special-treatment "
                "or untradeable issues, but the probed master does not provide "
                "a dated eligibility/status field sufficient for that rule."
            ),
        ),
        _capability(
            "daily_ohlcv",
            (
                "AVAILABLE"
                if bar_ok and {"O", "H", "L", "C", "Vo"}.issubset(bar_fields)
                else "PREMIUM_UNKNOWN"
            ),
            critical=True,
            evidence=["live_api:daily_bars", "official:personal_daily_bars"],
            note="Raw daily OHLC and volume were returned for bounded samples.",
        ),
        _capability(
            "traded_value",
            (
                "AVAILABLE"
                if bar_ok and "Va" in bar_fields
                else "PREMIUM_UNKNOWN"
            ),
            critical=True,
            evidence=["live_api:daily_bars", "official:personal_daily_bars"],
            note="Va (daily traded value) was returned.",
        ),
        _capability(
            "corporate_action_adjustment_factor",
            "PARTIAL" if adjustment_verified else "PREMIUM_UNKNOWN",
            critical=True,
            evidence=[
                "live_api:corporate_action_samples",
                "official:personal_adjustment_logic",
            ],
            note=(
                "All three official split/reverse-split examples matched and "
                "passed continuity checks. This does not establish comprehensive "
                "coverage of rights issues or other corporate actions."
            ),
        ),
        _capability(
            "raw_and_adjusted_ohlc",
            (
                "AVAILABLE"
                if bar_ok
                and {
                    "O",
                    "H",
                    "L",
                    "C",
                    "AdjO",
                    "AdjH",
                    "AdjL",
                    "AdjC",
                }.issubset(bar_fields)
                else "PREMIUM_UNKNOWN"
            ),
            critical=False,
            evidence=["live_api:daily_bars", "official:personal_daily_bars"],
            note="Both raw and split-adjusted OHLC fields were returned.",
        ),
        _capability(
            "dividend_return_identification",
            "PARTIAL",
            critical=False,
            evidence=[
                "official:personal_adjustment_logic",
                "official:personal_data_periods",
            ],
            note=(
                "Daily adjusted prices exclude dividends. Premium provides a "
                "separate dividend dataset from 2013-02-20, but no ready-made "
                "total-return series for the full 2008-start price period."
            ),
        ),
        _capability(
            "reproducible_historical_snapshot",
            "SUPPORT_CONFIRMATION_REQUIRED",
            critical=True,
            evidence=["official:personal_terms", "live_api:response_hashes"],
            note=(
                "Responses can be hashed locally, but persistent versioned "
                "storage is not given an explicit safe harbor. The terms impose "
                "deletion duties after specified cancellation paths and do not "
                "clearly authorize publishing raw, processed, or hash snapshots."
            ),
        ),
        _capability(
            "known_at_or_available_at_timestamp",
            "NOT_AVAILABLE",
            critical=True,
            evidence=["official:personal_eq_master", "live_api:master_fields"],
            note=(
                "The master exposes an effective Date, not a versioned known-at "
                "or publication timestamp."
            ),
        ),
        _capability(
            "full_frozen_u15_period_coverage",
            "PARTIAL",
            critical=False,
            evidence=[
                "official:personal_data_periods",
                "local:u15_summary_period",
            ],
            note=(
                "Personal Premium begins at 2008-05-07, while the frozen U15 "
                "effective period begins in 2004. A split/reverse-split-adjusted "
                "common-period exploratory rerun is technically possible, but "
                "an exact or comprehensive-action replacement is not."
            ),
        ),
    ]

    critical_failures = [
        item["id"]
        for item in capabilities
        if item["critical_for_formal_u50_u100"]
        and item["status"] != "AVAILABLE"
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "audit_id": summary["audit_id"],
        "base_commit": summary["base_commit"],
        "evidence_type": summary["evidence_type"],
        "api_version": API_VERSION,
        "api_call_count": summary["api_calls"]["used"],
        "capabilities": capabilities,
        "critical_failures": critical_failures,
        "capability_verdict": (
            "PIT_READY"
            if not critical_failures
            else "PRO_OR_ALTERNATIVE_REQUIRED"
        ),
        "formal_u50_u100_possible": not critical_failures,
        "formal_u50_u100_possible_with_current_personal_v2": (
            not critical_failures
        ),
        "formal_u50_u100_authorized": False,
        "u50_u100_backtest_executed": False,
        "premium_recommendation": (
            "MAINTAIN_PENDING_SUPPORT_AND_APPROVED_ARCHIVAL_GATE"
        ),
        "standard_downgrade_recommendation": "DO_NOT_DOWNGRADE_YET",
        "u15_adjusted_rerun": {
            "formal_capability_possible": False,
            "comprehensive_common_period_rerun_possible": False,
            "split_reverse_split_adjusted_common_period_rerun_possible": bool(
                adjustment_verified
                and {"AdjO", "AdjH", "AdjL", "AdjC"}.issubset(bar_fields)
            ),
            "full_frozen_period_possible": False,
            "formal_corporate_action_complete": False,
            "comprehensive_corporate_action_coverage_established": False,
            "verified_adjustment_scope": "SPLIT_AND_REVERSE_SPLIT_EXAMPLES_ONLY",
            "classification": (
                "EXPLORATORY_CAPABILITY_ONLY_NOT_FORMAL_OR_AUTHORIZED"
            ),
            "provider_earliest_date": "2008-05-07",
            "authorized_in_this_gate": False,
        },
    }


def _find_probe(
    probes: Sequence[Mapping[str, Any]], probe_id: str
) -> Mapping[str, Any]:
    return next(item for item in probes if item["probe_id"] == probe_id)


def _decision_from_matrix(matrix: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "capability_verdict": matrix["capability_verdict"],
        "formal_u50_u100_possible": matrix["formal_u50_u100_possible"],
        "formal_u50_u100_authorized": False,
        "u50_u100_backtest_executed": False,
        "premium_recommendation": matrix["premium_recommendation"],
        "standard_downgrade_recommendation": matrix[
            "standard_downgrade_recommendation"
        ],
        "u15_adjusted_rerun": matrix["u15_adjusted_rerun"],
    }


def _legal_classification() -> dict[str, Any]:
    return {
        "ephemeral_local_processing_for_own_use": (
            "AVAILABLE_FOR_NONCOMMERCIAL_NONACADEMIC_PERSONAL_OWN_USE"
        ),
        "persistent_versioned_local_storage": (
            "SUPPORT_CONFIRMATION_REQUIRED_WITH_CANCELLATION_DELETION_DUTY"
        ),
        "public_github_raw_commit": "NOT_PERMITTED",
        "private_github_raw_commit": "SUPPORT_CONFIRMATION_REQUIRED_AVOID",
        "aggregate_or_hash_publication": "SUPPORT_CONFIRMATION_REQUIRED",
        "committed_metadata_scope": (
            "ONE_TIME_BOUNDED_AUDIT_METADATA_UNDER_EXPLICIT_RESEARCH_GATE"
        ),
        "general_publication_safe_harbor_claimed": False,
        "third_party_distribution": "NOT_PERMITTED",
        "support_contact": "j-quants@jpx.co.jp",
        "terms_last_updated": "2026-01-19",
        "terms_priority": (
            "TERMS_OVERRIDE_FAQ_AND_JAPANESE_TEXT_PREVAILS"
        ),
    }


def _normalize_sanitized_summary(summary: MutableMapping[str, Any]) -> None:
    """Refresh derived metadata without requiring raw provider rows."""

    summary["official_sources"] = list(OFFICIAL_SOURCES)
    summary["legal_classification"] = _legal_classification()
    api_calls = summary["api_calls"]
    api_calls["counter_scope"] = (
        "AUDIT_TOTAL_WHEN_PRIOR_ATTEMPTS_IS_CARRIED_ACROSS_PROCESSES"
    )
    api_calls["cross_process_counter_persistence"] = "CALLER_SUPPLIED"

    probe_groups = (
        (summary["listed_issue_master"]["probes"], MASTER_REQUIRED_FIELDS),
        (summary["daily_bars"]["probes"], BAR_REQUIRED_FIELDS),
    )
    for probes, required_fields in probe_groups:
        for item in probes:
            fields = set(item["fields"])
            row_count = int(item["row_count"])
            null_counts = item["null_counts"]
            all_null = sorted(
                field
                for field in required_fields
                if field in fields
                and row_count > 0
                and int(null_counts.get(field, 0)) == row_count
            )
            item["all_null_required_fields"] = all_null
            if item["status"] == "ok" and (
                item["missing_required_fields"] or all_null
            ):
                item["status"] = "schema_mismatch"

    for item in summary["listed_issue_master"]["probes"]:
        requested = item["parameters"].get("date")
        if requested:
            expected = f"{requested[:4]}-{requested[4:6]}-{requested[6:]}"
            item["requested_snapshot_date_match"] = (
                item["min_date"] == expected and item["max_date"] == expected
            )
        else:
            item["requested_snapshot_date_match"] = None

    specs_by_probe = {
        item["probe_id"]: item for item in BAR_PROBES if "action_type" in item
    }
    for item in summary["daily_bars"]["probes"]:
        spec = specs_by_probe.get(item["probe_id"])
        if spec is None:
            continue
        expected = float(spec["expected_adjustment_factor"])
        item["expected_adjustment_factor"] = expected
        metrics = item["corporate_action_metrics"]
        observed_min = _as_number(metrics["adjustment_factor_min"])
        observed_max = _as_number(metrics["adjustment_factor_max"])
        metrics["official_factor_match"] = any(
            value is not None and abs(value - expected) <= 1e-12
            for value in (observed_min, observed_max)
        )


def run_live_probe(
    api_key: str,
    *,
    audit_as_of: str,
    base_commit: str = BASE_COMMIT,
    transport: Transport | None = None,
    request_limit: int = MAX_API_REQUESTS,
    prior_attempts: int = 0,
    min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    temp_root: Path = Path("/tmp"),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the fixed capability plan and return sanitized artifacts."""

    if not api_key:
        raise ValueError("API key is required")
    safe_temp_root = validate_temp_root(temp_root)
    budget = RequestBudget(request_limit, initial_used=prior_attempts)
    limiter = RateLimiter(min_interval_seconds)
    client = SafeApiClient(
        api_key,
        transport=transport or UrlLibTransport(),
        budget=budget,
        rate_limiter=limiter,
        timeout_seconds=timeout_seconds,
    )

    audit_id = (
        f"tgs-stable-v2-data-reality-{audit_as_of}-"
        f"{base_commit[:12]}"
    )
    master_rows_by_probe: dict[str, list[dict[str, Any]]] = {}
    master_summaries: list[dict[str, Any]] = []
    bar_summaries: list[dict[str, Any]] = []
    raw_files_created = 0

    temp_directory = tempfile.TemporaryDirectory(
        prefix="tgs-jquants-v2-",
        dir=safe_temp_root,
    )
    raw_directory = Path(temp_directory.name)
    try:
        for spec in MASTER_PROBES:
            rows, metadata = client.get_paginated(
                "/equities/master",
                spec["parameters"],
                raw_directory=raw_directory,
                probe_id=spec["probe_id"],
            )
            master_rows_by_probe[spec["probe_id"]] = rows
            master_summaries.append(
                _summarize_rows(
                    rows,
                    metadata,
                    probe_id=spec["probe_id"],
                    endpoint="/equities/master",
                    parameters=spec["parameters"],
                    required_fields=MASTER_REQUIRED_FIELDS,
                )
            )

        for spec in BAR_PROBES:
            rows, metadata = client.get_paginated(
                "/equities/bars/daily",
                spec["parameters"],
                raw_directory=raw_directory,
                probe_id=spec["probe_id"],
            )
            result = _summarize_rows(
                rows,
                metadata,
                probe_id=spec["probe_id"],
                endpoint="/equities/bars/daily",
                parameters=spec["parameters"],
                required_fields=BAR_REQUIRED_FIELDS,
            )
            result["purpose"] = spec["purpose"]
            result["official_source"] = spec["official_source"]
            if "action_type" in spec:
                result["action_type"] = spec["action_type"]
                result["official_effective_date"] = spec[
                    "official_effective_date"
                ]
                result["official_ratio"] = spec["official_ratio"]
                result["expected_adjustment_factor"] = spec[
                    "expected_adjustment_factor"
                ]
                result["corporate_action_metrics"] = _corporate_action_metrics(
                    rows,
                    expected_adjustment_factor=spec[
                        "expected_adjustment_factor"
                    ],
                )
            if "official_delisting_date" in spec:
                result["official_delisting_date"] = spec[
                    "official_delisting_date"
                ]
            bar_summaries.append(result)

        raw_files_created = len(list(raw_directory.iterdir()))
    finally:
        temp_directory.cleanup()

    historical_codes = {
        str(row.get("Code"))
        for row in master_rows_by_probe.get("master_2020_04_01", [])
        if row.get("Code") not in (None, "")
    }
    latest_codes = {
        str(row.get("Code"))
        for row in master_rows_by_probe.get("master_latest", [])
        if row.get("Code") not in (None, "")
    }
    delisted_code = "78290"
    delisted_bar_probe = _find_probe(bar_summaries, "bars_delisted_7829")
    historical_presence = delisted_code in historical_codes
    latest_presence = delisted_code in latest_codes
    delisted_bars_available = delisted_bar_probe["status"] == "ok"

    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "audit_id": audit_id,
        "audit_as_of": audit_as_of,
        "base_commit": base_commit,
        "evidence_type": "official_documentation_and_live_api_probe",
        "api_version": API_VERSION,
        "authentication": {
            "environment_variable": API_KEY_ENV,
            "header": API_KEY_HEADER,
            "secret_recorded": False,
            "status": (
                "succeeded"
                if any(
                    200 in item["http_statuses"]
                    for item in master_summaries + bar_summaries
                )
                else "not_verified"
            ),
        },
        "api_calls": {
            "hard_limit": MAX_API_REQUESTS,
            "configured_limit": request_limit,
            "used": budget.used,
            "remaining": request_limit - budget.used,
            "retries": 0,
            "prior_failed_attempts": prior_attempts,
            "min_interval_seconds": min_interval_seconds,
        },
        "probe_scope": {
            "full_market_full_history_downloaded": False,
            "large_csv_downloaded": False,
            "u50_u100_backtest_executed": False,
            "endpoints": sorted(ALLOWED_ENDPOINTS),
        },
        "listed_issue_master": {
            "probes": master_summaries,
            "historical_date_parameter_supported": all(
                item["status"] == "ok"
                for item in master_summaries
                if item["parameters"]
            ),
            "official_earliest_available_date": "2008-05-07",
            "non_business_date_rule": "next_business_day_snapshot",
        },
        "delisted_issue_example": {
            "code": delisted_code,
            "source_classification": "official_public_jpx_delisting_notice",
            "official_delisting_date": "2024-06-27",
            "official_source": (
                "https://www.jpx.co.jp/news/1023/20240626-11.html"
            ),
            "present_in_2020_04_01_master": historical_presence,
            "present_in_latest_master": latest_presence,
            "bounded_daily_bars_available": delisted_bars_available,
            "historical_presence_verified": (
                historical_presence
                and not latest_presence
                and delisted_bars_available
            ),
        },
        "daily_bars": {"probes": bar_summaries},
        "raw_response_handling": {
            "temporary_root": str(temp_root),
            "inside_repository": False,
            "files_created": raw_files_created,
            "retained": False,
            "disposition": "deleted_after_parse",
        },
        "legal_classification": _legal_classification(),
        "official_sources": list(OFFICIAL_SOURCES),
    }
    _normalize_sanitized_summary(summary)
    matrix = build_capability_matrix(summary)
    summary["decision"] = _decision_from_matrix(matrix)
    return summary, matrix


def _validated_output_path(path: Path) -> Path:
    root = DEFAULT_RESULTS_DIR.resolve()
    resolved = path.resolve()
    if resolved.parent != root:
        raise OutputPathError(
            f"output must be a direct child of {DEFAULT_RESULTS_DIR}"
        )
    return resolved


def write_json_artifact(path: Path, payload: Mapping[str, Any]) -> None:
    target = _validated_output_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bounded J-Quants V2 capability probe. Without --live this only "
            "prints the fixed plan and performs no environment access, file "
            "write, or network request."
        )
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="execute the fixed GET-only probe",
    )
    parser.add_argument(
        "--rebuild-from-sanitized-summary",
        action="store_true",
        help=(
            "offline-only: rebuild decisions and the matrix from the existing "
            "sanitized summary without reading credentials or using network"
        ),
    )
    parser.add_argument(
        "--audit-as-of",
        help="required with --live; explicit YYYY-MM-DD audit date",
    )
    parser.add_argument(
        "--base-commit",
        default=BASE_COMMIT,
        help="base commit recorded in sanitized artifacts",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=DEFAULT_RESULTS_DIR / "jquants_probe_summary.json",
    )
    parser.add_argument(
        "--matrix-output",
        type=Path,
        default=DEFAULT_RESULTS_DIR / "jquants_capability_matrix.json",
    )
    parser.add_argument(
        "--request-limit",
        type=int,
        default=MAX_API_REQUESTS,
        help=f"hard-capped at {MAX_API_REQUESTS}",
    )
    parser.add_argument(
        "--prior-attempts",
        type=int,
        default=0,
        help="failed attempts from this audit that must still count toward the cap",
    )
    parser.add_argument(
        "--min-interval-seconds",
        type=float,
        default=DEFAULT_MIN_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--temp-root",
        type=Path,
        default=Path("/tmp"),
        help="external root for automatically deleted raw responses",
    )
    return parser


def _dry_run_plan() -> dict[str, Any]:
    return {
        "mode": "dry_run",
        "api_version": API_VERSION,
        "authentication_environment_variable": API_KEY_ENV,
        "authentication_read": False,
        "network_requests": 0,
        "files_written": 0,
        "hard_request_limit": MAX_API_REQUESTS,
        "planned_logical_probes": len(MASTER_PROBES) + len(BAR_PROBES),
        "u50_u100_backtest": "not_in_scope",
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    transport: Transport | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    if args.live and args.rebuild_from_sanitized_summary:
        print(
            "ERROR: choose either --live or --rebuild-from-sanitized-summary.",
            file=sys.stderr,
        )
        return 2
    if args.rebuild_from_sanitized_summary:
        try:
            summary_path = _validated_output_path(args.summary_output)
            matrix_path = _validated_output_path(args.matrix_output)
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ProbeError("sanitized summary must be a JSON object")
            _normalize_sanitized_summary(loaded)
            matrix = build_capability_matrix(loaded)
            loaded["decision"] = _decision_from_matrix(matrix)
            write_json_artifact(summary_path, loaded)
            write_json_artifact(matrix_path, matrix)
        except (OSError, json.JSONDecodeError, ProbeError) as exc:
            print(f"ERROR: sanitized rebuild failed: {exc}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    "status": "rebuilt_from_sanitized_summary",
                    "network_requests": 0,
                    "authentication_read": False,
                    "api_calls_used": loaded["api_calls"]["used"],
                    "capability_verdict": matrix["capability_verdict"],
                },
                sort_keys=True,
            )
        )
        return 0
    if not args.live:
        print(json.dumps(_dry_run_plan(), sort_keys=True))
        return 0

    if not args.audit_as_of:
        print(
            "ERROR: --audit-as-of YYYY-MM-DD is required for a live probe.",
            file=sys.stderr,
        )
        return 2
    if args.request_limit > MAX_API_REQUESTS or args.request_limit < 0:
        print(
            f"ERROR: --request-limit must be between 0 and {MAX_API_REQUESTS}.",
            file=sys.stderr,
        )
        return 2
    if args.prior_attempts < 0 or args.prior_attempts > args.request_limit:
        print(
            "ERROR: --prior-attempts must be within the request limit.",
            file=sys.stderr,
        )
        return 2
    if args.min_interval_seconds < 0:
        print("ERROR: request interval cannot be negative.", file=sys.stderr)
        return 2

    environment = os.environ if environ is None else environ
    api_key = environment.get(API_KEY_ENV, "")
    if not api_key:
        print(
            "ERROR: JQUANTS_API_KEY is not set. Use a hidden shell prompt, "
            "export it only for this process, and do not write it to a file.",
            file=sys.stderr,
        )
        return 2

    try:
        summary_path = _validated_output_path(args.summary_output)
        matrix_path = _validated_output_path(args.matrix_output)
        summary, matrix = run_live_probe(
            api_key,
            audit_as_of=args.audit_as_of,
            base_commit=args.base_commit,
            transport=transport,
            request_limit=args.request_limit,
            prior_attempts=args.prior_attempts,
            min_interval_seconds=args.min_interval_seconds,
            temp_root=args.temp_root,
        )
        write_json_artifact(summary_path, summary)
        write_json_artifact(matrix_path, matrix)
    except ProbeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "completed",
                "api_calls_used": summary["api_calls"]["used"],
                "raw_responses_retained": False,
                "summary_output": str(summary_path),
                "matrix_output": str(matrix_path),
                "capability_verdict": matrix["capability_verdict"],
                "formal_u50_u100_possible": matrix[
                    "formal_u50_u100_possible"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
