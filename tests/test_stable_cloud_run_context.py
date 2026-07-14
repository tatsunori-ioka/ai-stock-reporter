from __future__ import annotations

import unittest
from datetime import date, datetime

from stable_cloud_run_context import (
    SCHEDULE_RESOLUTION_POLICY,
    SOURCE_EXTERNAL_SCHEDULER,
    SOURCE_LOCAL_DEFAULT_JST,
    SOURCE_MANUAL_INPUT,
    SOURCE_SCHEDULED_CUTOFF,
    SUPPORTED_SCHEDULE_CRON,
    latest_prior_cutoff,
    resolve_run_context,
)


class RunContextTests(unittest.TestCase):
    def resolve_schedule(self, started_at: str):
        return resolve_run_context(
            trigger_event="schedule",
            as_of="",
            scheduled_cron=SUPPORTED_SCHEDULE_CRON,
            schedule_timezone_name="Asia/Tokyo",
            run_started_at=started_at,
            trigger_origin="github_schedule",
            dispatch_key="",
        )

    def test_schedule_same_day_start_uses_same_cutoff_date(self) -> None:
        context = self.resolve_schedule("2026-07-06T11:20:00+00:00")

        self.assertEqual(date(2026, 7, 6), context.requested_as_of)
        self.assertEqual(SOURCE_SCHEDULED_CUTOFF, context.requested_as_of_source)
        self.assertEqual(SCHEDULE_RESOLUTION_POLICY, context.schedule_resolution_policy)

    def test_schedule_next_day_early_start_uses_prior_cutoff_date(self) -> None:
        context = self.resolve_schedule("2026-07-06T18:30:00+00:00")

        self.assertEqual(date(2026, 7, 6), context.requested_as_of)
        self.assertEqual("2026-07-07T03:30:00+09:00", context.run_started_at_jst)

    def test_friday_schedule_started_saturday_uses_friday(self) -> None:
        context = self.resolve_schedule("2026-07-10T18:30:00+00:00")

        self.assertEqual(date(2026, 7, 10), context.requested_as_of)

    def test_japan_holiday_is_not_shifted_to_prior_trading_day(self) -> None:
        context = self.resolve_schedule("2026-07-20T18:30:00+00:00")

        self.assertEqual(date(2026, 7, 20), context.requested_as_of)

    def test_manual_explicit_date_uses_manual_input(self) -> None:
        context = resolve_run_context(
            trigger_event="workflow_dispatch",
            as_of="2026-07-09",
            scheduled_cron="",
            schedule_timezone_name="",
            run_started_at="2026-07-09T12:00:00+00:00",
            trigger_origin="manual_ui",
            dispatch_key="",
        )

        self.assertEqual(date(2026, 7, 9), context.requested_as_of)
        self.assertEqual(SOURCE_MANUAL_INPUT, context.requested_as_of_source)
        self.assertEqual("manual_ui", context.trigger_origin)
        self.assertEqual("", context.dispatch_key)

    def test_cloudflare_dispatch_uses_external_scheduler_source(self) -> None:
        context = resolve_run_context(
            trigger_event="workflow_dispatch",
            as_of="2026-07-14",
            scheduled_cron="",
            schedule_timezone_name="",
            run_started_at="2026-07-14T08:00:00+00:00",
            trigger_origin="cloudflare_cron",
            dispatch_key="cloudflare_cron:2026-07-14T07:37:00.000Z",
        )

        self.assertEqual(date(2026, 7, 14), context.requested_as_of)
        self.assertEqual(SOURCE_EXTERNAL_SCHEDULER, context.requested_as_of_source)

    def test_cloudflare_dispatch_requires_dispatch_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "dispatch_key for cloudflare_cron"):
            resolve_run_context(
                trigger_event="workflow_dispatch",
                as_of="2026-07-14",
                scheduled_cron="",
                schedule_timezone_name="",
                run_started_at="2026-07-14T08:00:00+00:00",
                trigger_origin="cloudflare_cron",
                dispatch_key="",
            )

    def test_cloudflare_dispatch_date_must_match_key_jst_date(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match requested as_of"):
            resolve_run_context(
                trigger_event="workflow_dispatch",
                as_of="2026-07-15",
                scheduled_cron="",
                schedule_timezone_name="",
                run_started_at="2026-07-14T08:00:00+00:00",
                trigger_origin="cloudflare_cron",
                dispatch_key="cloudflare_cron:2026-07-14T07:37:00.000Z",
            )

    def test_manual_blank_date_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "as_of is required"):
            resolve_run_context(
                trigger_event="workflow_dispatch",
                as_of="",
                scheduled_cron="",
                schedule_timezone_name="",
                run_started_at="2026-07-09T12:00:00+00:00",
                trigger_origin="manual_ui",
                dispatch_key="",
            )

    def test_local_blank_date_uses_jst_start_date(self) -> None:
        context = resolve_run_context(
            trigger_event="local",
            as_of="",
            scheduled_cron="",
            schedule_timezone_name="",
            run_started_at="2026-07-09T16:00:00+00:00",
            trigger_origin="local_cli",
            dispatch_key="",
        )

        self.assertEqual(date(2026, 7, 10), context.requested_as_of)
        self.assertEqual(SOURCE_LOCAL_DEFAULT_JST, context.requested_as_of_source)

    def test_invalid_cron_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported scheduled cron"):
            resolve_run_context(
                trigger_event="schedule",
                as_of="",
                scheduled_cron="0 11 * * 1-5",
                schedule_timezone_name="Asia/Tokyo",
                run_started_at="2026-07-06T18:30:00+00:00",
                trigger_origin="github_schedule",
                dispatch_key="",
            )

    def test_invalid_timezone_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "schedule timezone"):
            resolve_run_context(
                trigger_event="schedule",
                as_of="",
                scheduled_cron=SUPPORTED_SCHEDULE_CRON,
                schedule_timezone_name="Mars/Olympus",
                run_started_at="2026-07-06T18:30:00+00:00",
                trigger_origin="github_schedule",
                dispatch_key="",
            )

    def test_naive_datetime_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "naive datetime"):
            latest_prior_cutoff(
                datetime(2026, 7, 7, 3, 30),
                SUPPORTED_SCHEDULE_CRON,
                "Asia/Tokyo",
            )

    def test_blank_datetime_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone-aware datetime"):
            resolve_run_context(
                trigger_event="schedule",
                as_of="",
                scheduled_cron=SUPPORTED_SCHEDULE_CRON,
                schedule_timezone_name="Asia/Tokyo",
                run_started_at="",
                trigger_origin="github_schedule",
                dispatch_key="",
            )

    def test_unknown_trigger_event_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported trigger_event"):
            resolve_run_context(
                trigger_event="push",
                as_of="2026-07-09",
                scheduled_cron="",
                schedule_timezone_name="",
                run_started_at="2026-07-09T12:00:00+00:00",
                trigger_origin="manual_ui",
                dispatch_key="",
            )

    def test_log_fields_include_required_context(self) -> None:
        fields = self.resolve_schedule("2026-07-06T18:30:00+00:00").log_fields("2026-07-06", "current")

        self.assertEqual(
            {
                "trigger_event",
                "trigger_origin",
                "dispatch_key",
                "scheduled_cron",
                "schedule_timezone",
                "run_started_at_jst",
                "requested_as_of",
                "requested_as_of_source",
                "schedule_resolution_policy",
                "data_date",
                "freshness_status",
            },
            set(fields),
        )


if __name__ == "__main__":
    unittest.main()
