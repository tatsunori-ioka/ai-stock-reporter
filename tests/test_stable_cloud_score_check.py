from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


if "pandas" not in sys.modules:
    try:
        __import__("pandas")
    except ModuleNotFoundError:
        sys.modules["pandas"] = types.ModuleType("pandas")
if "yfinance" not in sys.modules:
    try:
        __import__("yfinance")
    except ModuleNotFoundError:
        sys.modules["yfinance"] = types.ModuleType("yfinance")

import stable_cloud_score_check as score_check


def summary(*, freshness: str = "current") -> score_check.ScoreSummary:
    return score_check.ScoreSummary(
        as_of="2026-07-09",
        run_date="2026-07-09",
        requested_as_of="2026-07-09",
        data_date="2026-07-09",
        freshness_status=freshness,
        rows_scored=15,
        signal_count=0,
        raw_signal_count=0,
        max_score_ticker="6367.T",
        max_score=70,
        status="no_signal",
        source_file="stable_daily_score_check_2026_07_09.csv",
        note="",
    )


class ScoreCheckTests(unittest.TestCase):
    def test_matching_requested_as_of_and_data_date_is_current(self) -> None:
        self.assertEqual("current", score_check.freshness_status(date(2026, 7, 9), date(2026, 7, 9)))

    def test_requested_as_of_data_date_mismatch_is_stale(self) -> None:
        self.assertEqual("stale", score_check.freshness_status(date(2026, 7, 9), date(2026, 7, 8)))
        self.assertEqual("stale", score_check.freshness_status(date(2026, 7, 9), date(2026, 7, 10)))

    def test_no_data_is_not_formal_no_signal(self) -> None:
        rows = [
            {
                "data_status": "no_price_data",
                "freshness_status": "no_data",
                "stable_score": "",
                "data_date": "",
                "ticker": "6273.T",
            }
        ]

        result = score_check.score_summary(
            rows,
            "stable_daily_score_check_2026_07_09.csv",
            date(2026, 7, 9),
            "2026-07-09 20:17:00",
        )

        self.assertEqual("no_data", result.freshness_status)
        self.assertEqual("data_unavailable", result.status)
        self.assertNotEqual("no_signal", result.status)
        self.assertEqual(0, result.signal_count)

    def test_stale_signal_is_not_counted(self) -> None:
        rows = [
            {
                "data_status": "ok",
                "freshness_status": "stale",
                "stable_score": "100",
                "data_date": "2026-07-08",
                "ticker": "6273.T",
            }
        ]

        result = score_check.score_summary(
            rows,
            "stable_daily_score_check_2026_07_09.csv",
            date(2026, 7, 9),
            "2026-07-09 20:17:00",
        )

        self.assertEqual("data_stale", result.status)
        self.assertEqual(1, result.raw_signal_count)
        self.assertEqual(0, result.signal_count)

    def test_init_only_does_not_require_as_of(self) -> None:
        args = argparse.Namespace(
            as_of="",
            trigger_event="local",
            trigger_origin="local_cli",
            dispatch_key="",
            scheduled_cron="",
            schedule_timezone="",
            run_started_at="",
            execute=False,
            init_only=True,
            verify_only=False,
            out_dir=None,
            metadata=None,
            ledger_spreadsheet_id="",
            dashboard_spreadsheet_id="",
            skip_dashboard=False,
        )

        with patch.object(score_check, "parse_args", return_value=args), patch.object(
            score_check, "resolve_run_context"
        ) as resolver, contextlib.redirect_stdout(io.StringIO()):
            result = score_check.main()

        self.assertEqual(0, result)
        resolver.assert_not_called()

    def test_execute_manual_blank_fails_before_external_access(self) -> None:
        args = argparse.Namespace(
            as_of="",
            trigger_event="workflow_dispatch",
            trigger_origin="manual_ui",
            dispatch_key="",
            scheduled_cron="",
            schedule_timezone="",
            run_started_at="2026-07-09T12:00:00+00:00",
            execute=True,
            init_only=False,
            verify_only=False,
            out_dir=None,
            metadata=None,
            ledger_spreadsheet_id="ledger",
            dashboard_spreadsheet_id="dashboard",
            skip_dashboard=False,
        )

        with patch.object(score_check, "parse_args", return_value=args), patch.object(
            score_check, "build_score_rows"
        ) as market_data, patch.object(score_check, "build_sheets_service") as sheets, contextlib.redirect_stderr(
            io.StringIO()
        ):
            result = score_check.main()

        self.assertEqual(1, result)
        market_data.assert_not_called()
        sheets.assert_not_called()

    def test_dry_run_manual_blank_fails_before_external_access(self) -> None:
        args = argparse.Namespace(
            as_of="",
            trigger_event="workflow_dispatch",
            trigger_origin="manual_ui",
            dispatch_key="",
            scheduled_cron="",
            schedule_timezone="",
            run_started_at="2026-07-09T12:00:00+00:00",
            execute=False,
            init_only=False,
            verify_only=False,
            out_dir=None,
            metadata=None,
            ledger_spreadsheet_id="",
            dashboard_spreadsheet_id="",
            skip_dashboard=False,
        )

        with patch.object(score_check, "parse_args", return_value=args), patch.object(
            score_check, "build_score_rows"
        ) as market_data, patch.object(score_check, "build_sheets_service") as sheets, contextlib.redirect_stderr(
            io.StringIO()
        ):
            result = score_check.main()

        self.assertEqual(1, result)
        market_data.assert_not_called()
        sheets.assert_not_called()

    def test_verify_only_does_not_require_as_of(self) -> None:
        args = argparse.Namespace(
            as_of="",
            trigger_event="local",
            trigger_origin="local_cli",
            dispatch_key="",
            scheduled_cron="",
            schedule_timezone="",
            run_started_at="",
            execute=False,
            init_only=False,
            verify_only=True,
            out_dir=None,
            metadata=None,
            ledger_spreadsheet_id="ledger",
            dashboard_spreadsheet_id="dashboard",
            skip_dashboard=False,
        )

        with patch.object(score_check, "parse_args", return_value=args), patch.object(
            score_check, "build_sheets_service", return_value=object()
        ) as sheets, patch.object(score_check, "verify_sheet_state", return_value={"ok": True}), patch.object(
            score_check, "resolve_run_context"
        ) as resolver, contextlib.redirect_stdout(io.StringIO()):
            result = score_check.main()

        self.assertEqual(0, result)
        sheets.assert_called_once_with()
        resolver.assert_not_called()

    def test_normal_ledger_update_writes_rows_only_to_phase1_output_tabs(self) -> None:
        forbidden = {
            "TGS_Pending",
            "TGS_Positions",
            "TGS_Trade_History",
            "TGS_Account",
            "TGS_Daily_Log",
        }

        with patch.object(score_check, "ensure_ledger_tabs"), patch.object(
            score_check, "upsert_rows", return_value={"inserted": 15, "updated": 0}
        ) as upsert, patch.object(score_check, "append_row") as append:
            score_check.update_ledger_sheet(
                object(),
                "ledger",
                "dashboard",
                [{"requested_as_of": "2026-07-09", "ticker": "6273.T"}],
                summary(),
                "2026-07-09 20:17:00",
                "run-id",
            )

        self.assertEqual("TGS_Daily_Score_Check", upsert.call_args.args[2])
        self.assertEqual("TGS_Run_Log", append.call_args.args[2])
        self.assertNotIn(upsert.call_args.args[2], forbidden)
        self.assertNotIn(append.call_args.args[2], forbidden)
        self.assertNotIn("trigger_origin", score_check.RUN_LOG_COLUMNS)
        self.assertNotIn("dispatch_key", score_check.RUN_LOG_COLUMNS)

    def test_execute_artifact_keeps_pending_and_real_trading_disabled(self) -> None:
        run_context = score_check.RunContext(
            trigger_event="workflow_dispatch",
            trigger_origin="cloudflare_cron",
            dispatch_key="cloudflare_cron:2026-07-09T07:37:00.000Z",
            scheduled_cron="",
            schedule_timezone="",
            run_started_at_jst="2026-07-09T16:37:00+09:00",
            requested_as_of=date(2026, 7, 9),
            requested_as_of_source="external_scheduler",
            schedule_resolution_policy="",
        )

        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(
                out_dir=Path(directory),
                execute=True,
                ledger_spreadsheet_id="ledger",
                dashboard_spreadsheet_id="dashboard",
            )
            output_dir = score_check.write_dry_run(
                args,
                [],
                summary(),
                run_context,
                "2026-07-09 16:37:00",
                "run-id",
            )
            payload = json.loads((output_dir / "payload.json").read_text(encoding="utf-8"))

        self.assertEqual("execute", payload["mode"])
        self.assertFalse(payload["rules"]["pending_registration_enabled"])
        self.assertFalse(payload["rules"]["real_trading_enabled"])

    def test_cloudflare_blank_dispatch_key_fails_before_external_access(self) -> None:
        args = argparse.Namespace(
            as_of="2026-07-14",
            trigger_event="workflow_dispatch",
            trigger_origin="cloudflare_cron",
            dispatch_key="",
            scheduled_cron="",
            schedule_timezone="",
            run_started_at="2026-07-14T08:00:00+00:00",
            execute=True,
            init_only=False,
            verify_only=False,
            out_dir=None,
            metadata=None,
            ledger_spreadsheet_id="ledger",
            dashboard_spreadsheet_id="dashboard",
            skip_dashboard=False,
        )

        with patch.object(score_check, "parse_args", return_value=args), patch.object(
            score_check, "build_score_rows"
        ) as market_data, patch.object(score_check, "build_sheets_service") as sheets, contextlib.redirect_stderr(
            io.StringIO()
        ):
            result = score_check.main()

        self.assertEqual(1, result)
        market_data.assert_not_called()
        sheets.assert_not_called()


if __name__ == "__main__":
    unittest.main()
