from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import pit_lite.pipeline as pipeline


RUN_ID = "synthetic-comparison-001"


class ProvenancePassed(RuntimeError):
    """Test sentinel raised immediately after all provenance gates."""


def write_private_provenance(
    run: Path,
    *,
    checkpoint_changes: dict[str, Any] | None = None,
    request_changes: dict[str, Any] | None = None,
    membership_run_id: str = RUN_ID,
    corrupt_request_hash: bool = False,
) -> None:
    request = {
        "run_id": RUN_ID,
        "attempts_used": 12,
        "external_prior_attempts": 3,
        "gate_attempts_used": 15,
        "hard_attempt_limit": 2997,
    }
    request.update(request_changes or {})
    checkpoint = {
        "stage": "complete",
        "run_id": RUN_ID,
        "contract_sha256": pipeline.sha256_file(pipeline.CONTRACT_PATH),
        "acquisition_implementation_sha256": (
            pipeline.acquisition_implementation_sha256()
        ),
        "request_audit_sha256": pipeline.canonical_sha256(request),
    }
    checkpoint.update(checkpoint_changes or {})
    if corrupt_request_hash:
        checkpoint["request_audit_sha256"] = "0" * 64
    membership = {
        "run_id": membership_run_id,
        "U15_ADJUSTED_STATIC": [],
        "U15_RAW_COMMON_PERIOD": [],
        "U50_PIT_LITE": {},
        "U100_PIT_LITE": {},
    }
    files = {
        run / "checkpoint" / "acquisition.json": checkpoint,
        run / "checkpoint" / "request_audit.json": request,
        run / "universe_membership" / "annual_membership.json": membership,
    }
    for path, payload in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")


def patch_private_preflight(monkeypatch, run: Path, *, filevault: bool = True) -> None:
    monkeypatch.setattr(
        pipeline,
        "validate_private_tree",
        lambda _root: run.parents[1],
    )
    monkeypatch.setattr(pipeline, "assert_private_path", lambda path: path)
    monkeypatch.setattr(pipeline, "filevault_is_active", lambda: filevault)
    monkeypatch.setattr(pipeline, "verify_protected_inputs", lambda: {})
    monkeypatch.setattr(pipeline, "verify_production_files", lambda: {})
    monkeypatch.setattr(
        pipeline,
        "_read_rows",
        lambda _path: (_ for _ in ()).throw(ProvenancePassed()),
    )


def test_run_comparison_accepts_complete_provenance_before_reading_market_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = tmp_path / "private" / "runs" / RUN_ID
    write_private_provenance(run)
    patch_private_preflight(monkeypatch, run)
    with pytest.raises(ProvenancePassed):
        pipeline.run_comparison(RUN_ID, run)


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("checkpoint_run_id", "private acquisition provenance mismatch"),
        ("contract_sha256", "private acquisition provenance mismatch"),
        ("acquisition_implementation", "private acquisition provenance mismatch"),
        ("request_audit_hash", "private request-audit provenance mismatch"),
        ("request_run_id", "private request-audit provenance mismatch"),
        ("attempts_over_absolute_limit", "private request-audit budget mismatch"),
        ("attempt_limit_partition", "private request-audit budget mismatch"),
        ("membership_run_id", "private membership run_id mismatch"),
        ("filevault", "FileVault is not active at comparison time"),
    ],
)
def test_run_comparison_provenance_mismatch_fails_closed(
    tmp_path: Path,
    monkeypatch,
    case: str,
    expected_error: str,
) -> None:
    run = tmp_path / "private" / "runs" / RUN_ID
    checkpoint_changes: dict[str, Any] = {}
    request_changes: dict[str, Any] = {}
    membership_run_id = RUN_ID
    corrupt_request_hash = False
    filevault = True
    if case == "checkpoint_run_id":
        checkpoint_changes["run_id"] = "other-run"
    elif case == "contract_sha256":
        checkpoint_changes["contract_sha256"] = "1" * 64
    elif case == "acquisition_implementation":
        checkpoint_changes["acquisition_implementation_sha256"] = "2" * 64
    elif case == "request_audit_hash":
        corrupt_request_hash = True
    elif case == "request_run_id":
        request_changes["run_id"] = "other-run"
    elif case == "attempts_over_absolute_limit":
        request_changes["gate_attempts_used"] = 3001
    elif case == "attempt_limit_partition":
        request_changes["hard_attempt_limit"] = 2996
    elif case == "membership_run_id":
        membership_run_id = "other-run"
    elif case == "filevault":
        filevault = False
    else:
        raise AssertionError(f"unknown case: {case}")
    write_private_provenance(
        run,
        checkpoint_changes=checkpoint_changes,
        request_changes=request_changes,
        membership_run_id=membership_run_id,
        corrupt_request_hash=corrupt_request_hash,
    )
    patch_private_preflight(monkeypatch, run, filevault=filevault)
    with pytest.raises(RuntimeError, match=expected_error):
        pipeline.run_comparison(RUN_ID, run)


def metric_payload() -> dict[str, Any]:
    return {
        "cagr": 0.12,
        "maximum_drawdown": -0.20,
        "profit_factor": 1.40,
        "expectancy_per_trade": 0.02,
        "trade_count": 10,
    }


def synthetic_report_inputs() -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    universes: dict[str, Any] = {}
    for universe_id in pipeline.UNIVERSE_IDS:
        universes[universe_id] = {
            "primary": metric_payload(),
            "frequency": {
                "raw_signal_frequency_per_year": 20.0,
                "accepted_entry_frequency_per_year": 10.0,
                "longest_no_signal_sessions": 40,
                "longest_no_signal_calendar_days": 60,
            },
            "optimistic_path_sensitivity": {"cagr": 0.14},
            "last_close_terminal_sensitivity": {"cagr": 0.13},
            "independent_trade_diagnostic": {"profit_factor": 1.50},
            "equal_notional_diagnostic": {"cagr": 0.11},
        }
    criteria = {
        "cagr_at_least_10pct": True,
        "maximum_drawdown_vs_u15": False,
        "top_ticker_trade_share_at_most_15pct": True,
    }
    summary = {
        "run_id": RUN_ID,
        "period": {
            "effective_start": "2014-04-01",
            "frozen_end": "2026-07-24",
        },
        "universes": universes,
        "economic_gate": {
            "verdict": "MIXED",
            "universes": {
                universe_id: {
                    "verdict": "MIXED",
                    "criteria_passed": 2,
                    "criteria_total": 3,
                    "criteria": dict(criteria),
                }
                for universe_id in ("U50_PIT_LITE", "U100_PIT_LITE")
            },
        },
        "u15_raw_minus_static_diagnostic": {"cagr_delta": -0.01},
    }
    split_rows = [
        {
            "universe_id": universe_id,
            "split": split,
            "profit_factor": 1.20,
            "expectancy_per_trade": 0.01,
            "trade_count": 4,
            "cross_boundary_excluded_count": 1,
        }
        for universe_id in pipeline.UNIVERSE_IDS
        for split in ("validation", "final_holdout")
    ]
    concentration = [
        {
            "universe_id": universe_id,
            "dimension": dimension,
            "top_bucket_trade_share": 0.10 if dimension == "ticker" else 0.25,
            "accepted_entry_count": 10,
        }
        for universe_id in pipeline.UNIVERSE_IDS
        for dimension in ("ticker", "sector")
    ]
    cost_rows = [
        {
            "universe_id": universe_id,
            "cost_scenario": cost,
            "cagr": 0.12,
            "maximum_drawdown": -0.20,
            "profit_factor": 1.40,
        }
        for universe_id in pipeline.UNIVERSE_IDS
        for cost in ("zero", "basic", "strict")
    ]
    annual_rows = [
        {
            "universe_id": universe_id,
            "year": year,
            "selected_count": count,
            "shortfall_count": 0,
        }
        for universe_id, count in (
            ("U50_PIT_LITE", 50),
            ("U100_PIT_LITE", 100),
        )
        for year in (2014, 2026)
    ]
    request_summary = {
        "attempts_used": 700,
        "external_prior_attempts": 3,
        "gate_attempts_used": 703,
        "absolute_gate_attempt_limit": 3000,
        "estimated_expected_attempts": 724,
        "planned_worst_case_attempts": 2373,
        "filevault_active_at_comparison": True,
    }
    return (
        summary,
        split_rows,
        concentration,
        cost_rows,
        annual_rows,
        request_summary,
    )


def test_report_contains_all_decision_evidence_and_canonical_links() -> None:
    (
        summary,
        split_rows,
        concentration,
        cost_rows,
        annual_rows,
        request_summary,
    ) = synthetic_report_inputs()
    report = pipeline._build_report(
        summary,
        split_rows=split_rows,
        concentration=concentration,
        cost_rows=cost_rows,
        annual_rows=annual_rows,
        request_summary=request_summary,
    )
    required_fragments = [
        "## Validation and final holdout",
        "validation",
        "final_holdout",
        "## Exploratory economic gate",
        "`cagr_at_least_10pct`",
        "`maximum_drawdown_vs_u15`",
        "## Concentration",
        "Top ticker trade share",
        "Top sector trade share",
        "## Cost sensitivity",
        "| U50_PIT_LITE | zero |",
        "| U50_PIT_LITE | basic |",
        "| U50_PIT_LITE | strict |",
        "## Path, terminal and portfolio diagnostics",
        "Independent PF",
        "Equal-notional CAGR",
        "## Annual Universe counts",
        "Selection years are 2014–2026",
        "## API and licensed-data audit",
        "New-run HTTP attempts: 700",
        "Prior aborted-run attempts: 3",
        "Gate attempts used: 703 / 3000",
        "planned fallback worst case: 2373",
        "FileVault active at comparison: true",
        "The complete delisted-issue population is not guaranteed.",
        "U15 adjusted/static is survivorship-biased",
        "## Raw / adjusted U15 diagnostic",
    ]
    for fragment in required_fragments:
        assert fragment in report
    for filename in (
        "metrics_summary.json",
        "split_metrics.csv",
        "yearly_metrics.csv",
        "score_bucket_metrics.csv",
        "cost_sensitivity.csv",
        "concentration_metrics.csv",
        "universe_annual_counts.csv",
        "data_fingerprints.json",
        "request_audit_summary.json",
    ):
        assert f"../results/{filename}" in report
