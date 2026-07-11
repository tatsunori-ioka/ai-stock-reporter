#!/usr/bin/env python3
"""Resolve the immutable score date for a Cloud Phase1 run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


JST_NAME = "Asia/Tokyo"
SUPPORTED_SCHEDULE_CRON = "17 20 * * 1-5"
SCHEDULE_RESOLUTION_POLICY = "latest_prior_cutoff"

TRIGGER_SCHEDULE = "schedule"
TRIGGER_MANUAL = "workflow_dispatch"
TRIGGER_LOCAL = "local"
SUPPORTED_TRIGGER_EVENTS = {TRIGGER_SCHEDULE, TRIGGER_MANUAL, TRIGGER_LOCAL}

SOURCE_MANUAL_INPUT = "manual_input"
SOURCE_SCHEDULED_CUTOFF = "scheduled_cutoff"
SOURCE_LOCAL_DEFAULT_JST = "local_default_jst"


@dataclass(frozen=True)
class RunContext:
    trigger_event: str
    scheduled_cron: str
    schedule_timezone: str
    run_started_at_jst: str
    requested_as_of: date
    requested_as_of_source: str
    schedule_resolution_policy: str

    def log_fields(self, data_date: str = "", freshness_status: str = "") -> dict[str, str]:
        return {
            "trigger_event": self.trigger_event,
            "scheduled_cron": self.scheduled_cron,
            "schedule_timezone": self.schedule_timezone,
            "run_started_at_jst": self.run_started_at_jst,
            "requested_as_of": self.requested_as_of.isoformat(),
            "requested_as_of_source": self.requested_as_of_source,
            "schedule_resolution_policy": self.schedule_resolution_policy,
            "data_date": data_date,
            "freshness_status": freshness_status,
        }


def parse_score_date(value: str) -> date:
    text = value.strip()
    if not text:
        raise ValueError("as_of is required for workflow_dispatch score runs.")
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("as_of must use YYYY-MM-DD format.") from exc
    if parsed.isoformat() != text:
        raise ValueError("as_of must use YYYY-MM-DD format.")
    return parsed


def parse_aware_datetime(value: str) -> datetime:
    text = value.strip()
    if not text:
        raise ValueError("run_started_at must be an ISO 8601 timezone-aware datetime.")
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("run_started_at must be an ISO 8601 timezone-aware datetime.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("run_started_at must be timezone-aware; naive datetime is not supported.")
    return parsed


def schedule_timezone(name: str) -> ZoneInfo:
    if name != JST_NAME:
        raise ValueError(f"Unsupported schedule timezone: {name or '<empty>'}. Expected {JST_NAME}.")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid schedule timezone: {name}.") from exc


def latest_prior_cutoff(run_started_at: datetime, cron: str, timezone_name: str) -> tuple[date, datetime]:
    if run_started_at.tzinfo is None or run_started_at.utcoffset() is None:
        raise ValueError("run_started_at must be timezone-aware; naive datetime is not supported.")
    if cron != SUPPORTED_SCHEDULE_CRON:
        raise ValueError(
            f"Unsupported scheduled cron: {cron or '<empty>'}. Expected {SUPPORTED_SCHEDULE_CRON}."
        )

    local_start = run_started_at.astimezone(schedule_timezone(timezone_name))
    cutoff_time = time(hour=20, minute=17)
    candidate = local_start.date()
    if local_start.time().replace(tzinfo=None) < cutoff_time:
        candidate -= timedelta(days=1)

    # This policy knows weekdays only. JPX holidays intentionally remain target dates.
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate, local_start


def resolve_run_context(
    *,
    trigger_event: str,
    as_of: str,
    scheduled_cron: str,
    schedule_timezone_name: str,
    run_started_at: str,
) -> RunContext:
    if trigger_event not in SUPPORTED_TRIGGER_EVENTS:
        raise ValueError(f"Unsupported trigger_event: {trigger_event or '<empty>'}.")

    started_at = parse_aware_datetime(run_started_at)
    jst = schedule_timezone(JST_NAME)
    started_at_jst = started_at.astimezone(jst)

    if trigger_event == TRIGGER_SCHEDULE:
        if as_of.strip():
            raise ValueError("Scheduled runs do not accept an explicit as_of override.")
        requested_as_of, started_at_jst = latest_prior_cutoff(
            started_at,
            scheduled_cron,
            schedule_timezone_name,
        )
        source = SOURCE_SCHEDULED_CUTOFF
        policy = SCHEDULE_RESOLUTION_POLICY
        timezone_name = schedule_timezone_name
    elif trigger_event == TRIGGER_MANUAL:
        requested_as_of = parse_score_date(as_of)
        source = SOURCE_MANUAL_INPUT
        policy = ""
        timezone_name = ""
        scheduled_cron = ""
    else:
        if as_of.strip():
            requested_as_of = parse_score_date(as_of)
            source = SOURCE_MANUAL_INPUT
        else:
            requested_as_of = started_at_jst.date()
            source = SOURCE_LOCAL_DEFAULT_JST
        policy = ""
        timezone_name = ""
        scheduled_cron = ""

    return RunContext(
        trigger_event=trigger_event,
        scheduled_cron=scheduled_cron,
        schedule_timezone=timezone_name,
        run_started_at_jst=started_at_jst.isoformat(timespec="seconds"),
        requested_as_of=requested_as_of,
        requested_as_of_source=source,
        schedule_resolution_policy=policy,
    )
