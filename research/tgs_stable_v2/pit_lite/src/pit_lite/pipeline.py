from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from tgs_stable_v2.config import COST_SCENARIOS
from tgs_stable_v2.metrics import portfolio_metrics, trade_metrics

from .acquisition import acquisition_implementation_sha256
from .api import filevault_is_active
from .artifacts import write_csv, write_json
from .contract import (
    BASE_COMMIT,
    CLASSIFICATION,
    CONTRACT,
    CONTRACT_PATH,
    GATE_ID,
    MODEL_ID,
    PIT_ROOT,
    REPORT_PATH,
    RESULTS_ROOT,
    canonical_sha256,
    sha256_file,
    verify_production_files,
    verify_protected_inputs,
)
from .diagnostics import equal_notional_curve, independent_trades
from .execution import simulate_capital_proxy
from .manifest import build_deletion_manifest
from .metrics import (
    combined_metrics,
    concentration_rows,
    economic_gate,
    score_metric_rows,
    signal_frequency,
    split_metric_rows,
    chronological_splits,
    yearly_metric_rows,
)
from .safety import (
    assert_private_path,
    atomic_write_json,
    read_json as read_private_json,
    validate_private_tree,
)
from .schema import normalize_bars, normalize_master, validate_security_code
from .signals import (
    apply_membership,
    first_common_ready_session,
    signal_events,
    signal_frame_from_bars,
)
from .universe import annual_selection_schedule, trading_sessions


UNIVERSE_IDS = (
    "U15_ADJUSTED_STATIC",
    "U15_RAW_COMMON_PERIOD",
    "U50_PIT_LITE",
    "U100_PIT_LITE",
)


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    copy = frame.copy()
    for column in copy.columns:
        if pd.api.types.is_datetime64_any_dtype(copy[column]):
            copy[column] = copy[column].dt.strftime("%Y-%m-%d")
    copy = copy.astype(object).where(pd.notna(copy), None)
    return copy.to_dict(orient="records")


def _read_rows(path: Path) -> list[dict[str, Any]]:
    value = read_private_json(path)
    if not isinstance(value, list):
        raise RuntimeError(f"private row file has unexpected schema: {path.name}")
    return value


def _label(row: Mapping[str, Any], run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "gate_id": GATE_ID,
        "model_id": MODEL_ID,
        "base_commit": BASE_COMMIT,
        "classification": CLASSIFICATION,
        **dict(row),
    }


def _private_bundle_hash(run_directory: Path, first_part: str) -> str:
    entries = [
        (str(path.relative_to(run_directory)), sha256_file(path))
        for path in sorted((run_directory / first_part).rglob("*"))
        if path.is_file()
    ]
    return canonical_sha256(entries)


def _implementation_hash() -> str:
    entries = [
        (str(path.relative_to(PIT_ROOT)), sha256_file(path))
        for path in sorted(
            [
                *PIT_ROOT.joinpath("src").rglob("*.py"),
                *PIT_ROOT.joinpath("scripts").rglob("*.py"),
                *PIT_ROOT.joinpath("tests").rglob("*.py"),
            ]
        )
    ]
    return canonical_sha256(entries)


def _curve_portfolio_metrics(curve: pd.DataFrame) -> dict[str, Any]:
    adapted = curve.copy()
    adapted["exposure"] = (
        pd.to_numeric(adapted["active_positions"], errors="coerce") > 0
    ).astype(float)
    return portfolio_metrics(adapted)


def _pct(value: Any) -> str:
    return f"{float(value):.2%}" if value is not None else "n/a"


def _ratio(value: Any) -> str:
    return f"{float(value):.3f}" if value is not None else "n/a"


def _build_report(
    summary: Mapping[str, Any],
    *,
    split_rows: list[dict[str, Any]],
    concentration: list[dict[str, Any]],
    cost_rows: list[dict[str, Any]],
    annual_rows: list[dict[str, Any]],
    request_summary: Mapping[str, Any],
) -> str:
    rows = []
    for universe_id in UNIVERSE_IDS:
        metrics = summary["universes"][universe_id]["primary"]
        rows.append(
            "| {u} | {cagr} | {dd} | {pf} | {exp} | {n} |".format(
                u=universe_id,
                cagr=(
                    f"{metrics['cagr']:.2%}"
                    if metrics.get("cagr") is not None
                    else "n/a"
                ),
                dd=(
                    f"{metrics['maximum_drawdown']:.2%}"
                    if metrics.get("maximum_drawdown") is not None
                    else "n/a"
                ),
                pf=(
                    f"{metrics['profit_factor']:.3f}"
                    if metrics.get("profit_factor") is not None
                    else "n/a"
                ),
                exp=(
                    f"{metrics['expectancy_per_trade']:.2%}"
                    if metrics.get("expectancy_per_trade") is not None
                    else "n/a"
                ),
                n=metrics["trade_count"],
            )
        )
    gate_lines = []
    for universe_id, result in summary["economic_gate"]["universes"].items():
        gate_lines.append(
            f"- {universe_id}: **{result['verdict']}** "
            f"({result['criteria_passed']}/{result['criteria_total']} criteria; "
            "drawdown-vs-U15 is fail-closed pending a numeric threshold)"
        )
    frequencies = []
    for universe_id in UNIVERSE_IDS:
        item = summary["universes"][universe_id]["frequency"]
        frequencies.append(
            f"- {universe_id}: {item['raw_signal_frequency_per_year']:.2f} raw "
            f"events/year, {item['accepted_entry_frequency_per_year']:.2f} "
            f"accepted entries/year; longest no-signal period "
            f"{item['longest_no_signal_sessions']} sessions / "
            f"{item['longest_no_signal_calendar_days']} calendar days."
        )
    split_lookup = {
        (row["universe_id"], row["split"]): row for row in split_rows
    }
    split_lines = []
    for universe_id in UNIVERSE_IDS:
        for split_name in ("validation", "final_holdout"):
            item = split_lookup[(universe_id, split_name)]
            split_lines.append(
                "| {u} | {s} | {pf} | {exp} | {n} | {cross} |".format(
                    u=universe_id,
                    s=split_name,
                    pf=_ratio(item.get("profit_factor")),
                    exp=_pct(item.get("expectancy_per_trade")),
                    n=item["trade_count"],
                    cross=item["cross_boundary_excluded_count"],
                )
            )
    gate_criteria_lines = []
    for universe_id in ("U50_PIT_LITE", "U100_PIT_LITE"):
        criteria = summary["economic_gate"]["universes"][universe_id]["criteria"]
        for criterion, passed in criteria.items():
            gate_criteria_lines.append(
                f"| {universe_id} | `{criterion}` | "
                f"{'PASS' if passed else 'FAIL'} |"
            )
    concentration_lookup = {
        (row["universe_id"], row["dimension"]): row for row in concentration
    }
    concentration_lines = []
    for universe_id in UNIVERSE_IDS:
        ticker = concentration_lookup[(universe_id, "ticker")]
        sector = concentration_lookup[(universe_id, "sector")]
        concentration_lines.append(
            "| {u} | {ticker} | {sector} | {n} |".format(
                u=universe_id,
                ticker=_pct(ticker.get("top_bucket_trade_share")),
                sector=_pct(sector.get("top_bucket_trade_share")),
                n=ticker["accepted_entry_count"],
            )
        )
    cost_lines = []
    for row in cost_rows:
        cost_lines.append(
            "| {u} | {cost} | {cagr} | {dd} | {pf} |".format(
                u=row["universe_id"],
                cost=row["cost_scenario"],
                cagr=_pct(row.get("cagr")),
                dd=_pct(row.get("maximum_drawdown")),
                pf=_ratio(row.get("profit_factor")),
            )
        )
    sensitivity_lines = []
    for universe_id in UNIVERSE_IDS:
        item = summary["universes"][universe_id]
        sensitivity_lines.append(
            "| {u} | {primary} | {optimistic} | {terminal} | {independent} | "
            "{equal} |".format(
                u=universe_id,
                primary=_pct(item["primary"].get("cagr")),
                optimistic=_pct(
                    item["optimistic_path_sensitivity"].get("cagr")
                ),
                terminal=_pct(
                    item["last_close_terminal_sensitivity"].get("cagr")
                ),
                independent=_ratio(
                    item["independent_trade_diagnostic"].get("profit_factor")
                ),
                equal=_pct(item["equal_notional_diagnostic"].get("cagr")),
            )
        )
    annual_dynamic = [
        row
        for row in annual_rows
        if row["universe_id"] in {"U50_PIT_LITE", "U100_PIT_LITE"}
    ]
    annual_lines = []
    for universe_id in ("U50_PIT_LITE", "U100_PIT_LITE"):
        selected = [
            int(row["selected_count"])
            for row in annual_dynamic
            if row["universe_id"] == universe_id
        ]
        shortfall_years = sum(
            int(row["shortfall_count"]) > 0
            for row in annual_dynamic
            if row["universe_id"] == universe_id
        )
        annual_lines.append(
            f"| {universe_id} | {min(selected)}–{max(selected)} | "
            f"{shortfall_years} |"
        )
    raw_primary = summary["universes"]["U15_RAW_COMMON_PERIOD"]["primary"]
    adjusted_primary = summary["universes"]["U15_ADJUSTED_STATIC"]["primary"]
    return (
        "# PIT-lite U15/U50/U100 comparison report\n\n"
        f"- Gate: `{GATE_ID}`\n"
        f"- Base: `{BASE_COMMIT}`\n"
        f"- Run: `{summary['run_id']}`\n"
        f"- Classification: `{CLASSIFICATION}`\n"
        f"- Effective common period: {summary['period']['effective_start']} to "
        f"{summary['period']['frozen_end']}\n"
        "- Primary: basic cost, conservative same-day path, JPY 10 million "
        "fractional ten-slot proxy.\n\n"
        "This is Personal Premium PIT-lite exploratory evidence. It is not "
        "Formal U50/U100 and does not authorize a Formal Candidate, production "
        "change, purchase, or real-money canary.\n\n"
        "## Primary aggregate metrics\n\n"
        "| Universe | CAGR | Max DD | PF | Expectancy | Accepted entries |\n"
        "|---|---:|---:|---:|---:|---:|\n"
        + "\n".join(rows)
        + "\n\n## Frequency\n\n"
        + "\n".join(frequencies)
        + "\n\n## Validation and final holdout\n\n"
        "| Universe | Split | PF | Expectancy | Trades | Cross-boundary excluded |\n"
        "|---|---|---:|---:|---:|---:|\n"
        + "\n".join(split_lines)
        + "\n\n## Concentration\n\n"
        "| Universe | Top ticker trade share | Top sector trade share | Entries |\n"
        "|---|---:|---:|---:|\n"
        + "\n".join(concentration_lines)
        + "\n\n## Cost sensitivity\n\n"
        "| Universe | Cost | CAGR | Max DD | PF |\n"
        "|---|---|---:|---:|---:|\n"
        + "\n".join(cost_lines)
        + "\n\n## Path, terminal and portfolio diagnostics\n\n"
        "| Universe | Primary CAGR | Optimistic CAGR | Last-close CAGR | "
        "Independent PF | Equal-notional CAGR |\n"
        "|---|---:|---:|---:|---:|---:|\n"
        + "\n".join(sensitivity_lines)
        + "\n\n## Raw / adjusted U15 diagnostic\n\n"
        f"- Adjusted U15 CAGR / DD / PF: {_pct(adjusted_primary.get('cagr'))} / "
        f"{_pct(adjusted_primary.get('maximum_drawdown'))} / "
        f"{_ratio(adjusted_primary.get('profit_factor'))}\n"
        f"- Raw U15 CAGR / DD / PF: {_pct(raw_primary.get('cagr'))} / "
        f"{_pct(raw_primary.get('maximum_drawdown'))} / "
        f"{_ratio(raw_primary.get('profit_factor'))}\n"
        f"- Raw-minus-adjusted CAGR delta: "
        f"{_pct(summary['u15_raw_minus_static_diagnostic']['cagr_delta'])}\n"
        + "\n## Annual Universe counts\n\n"
        "Selection years are 2014–2026 (13 annual selections).\n\n"
        "| Universe | Selected count range | Shortfall years |\n"
        "|---|---:|---:|\n"
        + "\n".join(annual_lines)
        + "\n\n## API and licensed-data audit\n\n"
        f"- New-run HTTP attempts: {request_summary['attempts_used']}\n"
        f"- Prior aborted-run attempts: "
        f"{request_summary['external_prior_attempts']}\n"
        f"- Gate attempts used: {request_summary['gate_attempts_used']} / "
        f"{request_summary['absolute_gate_attempt_limit']}\n"
        f"- Expected attempts: {request_summary['estimated_expected_attempts']}; "
        f"planned fallback worst case: "
        f"{request_summary['planned_worst_case_attempts']}\n"
        f"- FileVault active at comparison: "
        f"{str(request_summary['filevault_active_at_comparison']).lower()}\n"
        "- Raw licensed data committed: false\n"
        "- Private cleanup: NOT_EXECUTED\n"
        + "\n\n## Exploratory economic gate\n\n"
        + f"- Overall: **{summary['economic_gate']['verdict']}**\n"
        + "\n".join(gate_lines)
        + "\n\n| Universe | Criterion | Result |\n"
        "|---|---|---|\n"
        + "\n".join(gate_criteria_lines)
        + "\n\nAn `EXPLORATORY_PROMISE_PASS` here would still have no promotion "
        "effect. The undefined "
        "“drawdown not significantly worse than U15” condition was frozen "
        "before results as `MANUAL_THRESHOLD_REQUIRED_FAIL_CLOSED`.\n\n"
        "## Data and method limitations\n\n"
        "- The complete delisted-issue population is not guaranteed.\n"
        "- U15 adjusted/static is survivorship-biased: the current 15 names "
        "are applied backward through history.\n"
        "- Active-issue, market and S33 sector values are effective-date "
        "snapshots; record-level known-at timestamps are unavailable.\n"
        "- Five-year history uses first observed bar, not listing date.\n"
        "- Corporate-group and complete special-treatment histories are "
        "unavailable and no substitute was inferred.\n"
        "- Historical trading units are unavailable; the fractional-notional "
        "capital proxy does not prove Japanese round-lot executability.\n"
        "- Codes are not stitched; comprehensive corporate-action coverage is "
        "not established; adjusted bars exclude dividends.\n"
        "- U15 raw is diagnostic only. Premature data ends use a 20% haircut in "
        "the primary and last-close in sensitivity.\n"
        "- Repository artifacts contain aggregates and non-reconstructible "
        "hashes only. Raw bars, annual members and exact ledgers remain in the "
        "FileVault-protected private root.\n\n"
        "## Authorization state\n\n"
        "- Formal U50/U100: not authorized\n"
        "- Formal Candidate: HOLD\n"
        "- Real-money canary: none\n"
        "- Premium recommendation: maintain through approved exploration; "
        "cleanup remains NOT_EXECUTED\n\n"
        "## Canonical aggregate artifacts\n\n"
        "- [`metrics_summary.json`](../results/metrics_summary.json)\n"
        "- [`split_metrics.csv`](../results/split_metrics.csv)\n"
        "- [`yearly_metrics.csv`](../results/yearly_metrics.csv)\n"
        "- [`score_bucket_metrics.csv`](../results/score_bucket_metrics.csv)\n"
        "- [`cost_sensitivity.csv`](../results/cost_sensitivity.csv)\n"
        "- [`concentration_metrics.csv`](../results/concentration_metrics.csv)\n"
        "- [`universe_annual_counts.csv`](../results/universe_annual_counts.csv)\n"
        "- [`data_fingerprints.json`](../results/data_fingerprints.json)\n"
        "- [`request_audit_summary.json`](../results/request_audit_summary.json)\n"
    )


def run_comparison(run_id: str, run_directory: Path) -> dict[str, Any]:
    private_root = validate_private_tree(run_directory.parents[1])
    assert_private_path(run_directory)
    filevault_active_now = filevault_is_active()
    if not filevault_active_now:
        raise RuntimeError("FileVault is not active at comparison time")
    verify_protected_inputs()
    production = verify_production_files()

    checkpoint = read_private_json(run_directory / "checkpoint" / "acquisition.json")
    expected_checkpoint = {
        "run_id": run_id,
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "acquisition_implementation_sha256": acquisition_implementation_sha256(),
    }
    checkpoint_mismatches = [
        key
        for key, expected in expected_checkpoint.items()
        if checkpoint.get(key) != expected
    ]
    if checkpoint.get("stage") != "complete" or checkpoint_mismatches:
        raise RuntimeError(
            "private acquisition provenance mismatch: "
            + ", ".join(["stage", *sorted(checkpoint_mismatches)])
        )
    request_private = read_private_json(
        run_directory / "checkpoint" / "request_audit.json"
    )
    if (
        checkpoint.get("request_audit_sha256")
        != canonical_sha256(request_private)
        or request_private.get("run_id") != run_id
    ):
        raise RuntimeError("private request-audit provenance mismatch")
    absolute_attempt_limit = int(CONTRACT["api"]["hard_attempt_limit"])
    external_prior_attempts = int(request_private.get("external_prior_attempts", 0))
    if (
        int(request_private["gate_attempts_used"]) > absolute_attempt_limit
        or int(request_private["hard_attempt_limit"]) + external_prior_attempts
        != absolute_attempt_limit
    ):
        raise RuntimeError("private request-audit budget mismatch")
    membership = read_private_json(
        run_directory / "universe_membership" / "annual_membership.json"
    )
    if membership.get("run_id") != run_id:
        raise RuntimeError("private membership run_id mismatch")
    calendar = pd.DataFrame(_read_rows(run_directory / "normalized" / "calendar.json"))
    calendar["Date"] = pd.to_datetime(calendar["Date"]).dt.tz_localize(None)
    all_sessions = trading_sessions(calendar)
    schedules = annual_selection_schedule(all_sessions)
    selection_dates = {item.year: item.selection_date for item in schedules}
    schedule_by_year = {item.year: item for item in schedules}

    masters: dict[int, pd.DataFrame] = {}
    sectors: dict[tuple[int, str], str] = {}
    for schedule in schedules:
        master = normalize_master(
            _read_rows(
                run_directory
                / "normalized"
                / "masters"
                / f"{schedule.year}.json"
            )
        )
        masters[schedule.year] = master
        for row in master.to_dict(orient="records"):
            sectors[(schedule.year, str(row["Code"]))] = str(row["S33"])

    required_codes = {
        validate_security_code(code)
        for code in membership["U15_ADJUSTED_STATIC"]
    }
    for universe_id in ("U50_PIT_LITE", "U100_PIT_LITE"):
        for codes in membership[universe_id].values():
            required_codes.update(validate_security_code(code) for code in codes)
    bars_by_code = {
        code: normalize_bars(
            _read_rows(run_directory / "normalized" / "bars" / f"{code}.json")
        )
        for code in sorted(required_codes)
    }

    adjusted_base = {
        code: signal_frame_from_bars(frame, basis="adjusted")
        for code, frame in bars_by_code.items()
    }
    u15_codes = set(membership["U15_ADJUSTED_STATIC"])
    raw_base = {
        code: signal_frame_from_bars(bars_by_code[code], basis="raw")
        for code in sorted(u15_codes)
    }
    frames: dict[str, dict[str, pd.DataFrame]] = {
        "U15_ADJUSTED_STATIC": {
            code: apply_membership(
                adjusted_base[code],
                code,
                static_codes=u15_codes,
            )
            for code in sorted(u15_codes)
        },
        "U15_RAW_COMMON_PERIOD": {
            code: apply_membership(raw_base[code], code, static_codes=u15_codes)
            for code in sorted(u15_codes)
        },
    }
    for universe_id in ("U50_PIT_LITE", "U100_PIT_LITE"):
        dynamic_codes = sorted(
            {
                code
                for annual in membership[universe_id].values()
                for code in annual
            }
        )
        frames[universe_id] = {
            code: apply_membership(
                adjusted_base[code],
                code,
                annual_membership=membership[universe_id],
                selection_dates=selection_dates,
            )
            for code in dynamic_codes
        }

    search_sessions = all_sessions[
        (all_sessions >= pd.Timestamp(schedules[0].selection_date))
        & (all_sessions <= pd.Timestamp(CONTRACT["period"]["frozen_end_date"]))
    ]
    effective_start = first_common_ready_session(
        search_sessions,
        frames,
        {
            "U15_ADJUSTED_STATIC": membership["U15_ADJUSTED_STATIC"],
            "U15_RAW_COMMON_PERIOD": membership["U15_RAW_COMMON_PERIOD"],
            "U50_PIT_LITE": membership["U50_PIT_LITE"],
            "U100_PIT_LITE": membership["U100_PIT_LITE"],
        },
        selection_dates,
    )
    evaluation_sessions = search_sessions[search_sessions >= effective_start]
    evaluation_end = pd.Timestamp(evaluation_sessions[-1])
    splits = chronological_splits(evaluation_sessions)

    signals_by_universe = {
        universe_id: signal_events(
            universe_frames,
            sectors,
            selection_dates,
            evaluation_start=effective_start,
            evaluation_end=evaluation_end,
        )
        for universe_id, universe_frames in frames.items()
    }

    primary_ledgers: dict[str, pd.DataFrame] = {}
    primary_curves: dict[str, pd.DataFrame] = {}
    primary_counters: dict[str, dict[str, int]] = {}
    universe_summary: dict[str, Any] = {}
    cost_rows: list[dict[str, Any]] = []
    yearly_rows: list[dict[str, Any]] = []
    split_rows: list[dict[str, Any]] = []
    score_rows: list[dict[str, Any]] = []
    concentration: list[dict[str, Any]] = []

    for universe_id in UNIVERSE_IDS:
        universe_frames = frames[universe_id]
        signals = signals_by_universe[universe_id]
        scenario_results: dict[str, tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]] = {}
        for cost_name in ("zero", "basic", "strict"):
            scenario_results[f"cost_{cost_name}"] = simulate_capital_proxy(
                signals,
                universe_frames,
                evaluation_sessions,
                cost=COST_SCENARIOS[cost_name],
                path_policy="conservative",
                terminal_policy="haircut_20",
            )
        scenario_results["path_optimistic"] = simulate_capital_proxy(
            signals,
            universe_frames,
            evaluation_sessions,
            cost=COST_SCENARIOS["basic"],
            path_policy="optimistic",
            terminal_policy="haircut_20",
        )
        scenario_results["terminal_last_close"] = simulate_capital_proxy(
            signals,
            universe_frames,
            evaluation_sessions,
            cost=COST_SCENARIOS["basic"],
            path_policy="conservative",
            terminal_policy="last_close",
        )
        primary_ledger, primary_curve, counters = scenario_results["cost_basic"]
        primary_ledgers[universe_id] = primary_ledger
        primary_curves[universe_id] = primary_curve
        primary_counters[universe_id] = counters

        independent, independent_counters = independent_trades(
            universe_id,
            universe_frames,
            evaluation_sessions,
            evaluation_start=effective_start,
            evaluation_end=evaluation_end,
            cost=COST_SCENARIOS["basic"],
            path_policy="conservative",
        )
        equal_curve = equal_notional_curve(
            independent,
            universe_frames,
            evaluation_start=effective_start,
            evaluation_end=evaluation_end,
        )
        private_root = run_directory / "trade_ledger"
        for scenario_name, (ledger, curve, _) in scenario_results.items():
            atomic_write_json(
                private_root / f"{universe_id}-{scenario_name}-ledger.json",
                _records(ledger),
            )
            atomic_write_json(
                private_root / f"{universe_id}-{scenario_name}-curve.json",
                _records(curve),
            )
        atomic_write_json(
            private_root / f"{universe_id}-independent-ledger.json",
            _records(independent),
        )
        atomic_write_json(
            private_root / f"{universe_id}-equal-notional-curve.json",
            _records(equal_curve),
        )

        primary_metrics = combined_metrics(primary_ledger, primary_curve, counters)
        frequency = signal_frequency(
            signals,
            primary_ledger,
            evaluation_sessions,
        )
        universe_summary[universe_id] = {
            "primary": primary_metrics,
            "frequency": frequency,
            "independent_trade_diagnostic": {
                **trade_metrics(independent),
                **independent_counters,
            },
            "equal_notional_diagnostic": _curve_portfolio_metrics(equal_curve),
            "optimistic_path_sensitivity": combined_metrics(
                *scenario_results["path_optimistic"][:2],
                scenario_results["path_optimistic"][2],
            ),
            "last_close_terminal_sensitivity": combined_metrics(
                *scenario_results["terminal_last_close"][:2],
                scenario_results["terminal_last_close"][2],
            ),
        }
        for cost_name in ("zero", "basic", "strict"):
            ledger, curve, current_counters = scenario_results[f"cost_{cost_name}"]
            cost_rows.append(
                _label(
                    {
                        "universe_id": universe_id,
                        "cost_scenario": cost_name,
                        "path_policy": "conservative",
                        "terminal_policy": "haircut_20",
                        **combined_metrics(ledger, curve, current_counters),
                    },
                    run_id,
                )
            )
        yearly_rows.extend(
            _label(row, run_id)
            for row in yearly_metric_rows(
                universe_id,
                signals,
                primary_ledger,
                primary_curve,
                effective_start.year,
                evaluation_end.year,
            )
        )
        split_rows.extend(
            _label(row, run_id)
            for row in split_metric_rows(
                universe_id,
                primary_ledger,
                primary_curve,
                splits,
            )
        )
        score_rows.extend(
            _label(row, run_id)
            for row in score_metric_rows(universe_id, signals, primary_ledger)
        )
        concentration.extend(
            _label(row, run_id)
            for row in concentration_rows(universe_id, primary_ledger)
        )

    gate = economic_gate(
        {key: value["primary"] for key, value in universe_summary.items()},
        split_rows,
        concentration,
    )
    summary = {
        "schema_version": "1.0",
        "run_id": run_id,
        "gate_id": GATE_ID,
        "model_id": MODEL_ID,
        "base_commit": BASE_COMMIT,
        "classification": CLASSIFICATION,
        "period": {
            "provider_earliest": CONTRACT["period"]["provider_earliest_date"],
            "effective_start": effective_start.date().isoformat(),
            "frozen_end": evaluation_end.date().isoformat(),
            "common_valid_session_count": len(evaluation_sessions),
            "split_method": "fixed chronological 60/20/20 common JPX sessions",
        },
        "authorizations": {
            "pit_lite_execution": True,
            "pit_lite_u50_u100": "EXECUTED",
            "formal_u50_u100": "NOT_AUTHORIZED",
            "formal_candidate": "HOLD",
            "real_money_canary": "none",
            "purchase_or_plan_change": False,
        },
        "universes": universe_summary,
        "economic_gate": gate,
        "research_engineering_gate": "PASS",
        "formal_u50_u100": "NOT_AUTHORIZED",
        "pit_lite_u50_u100": "EXECUTED",
        "private_cleanup": "NOT_EXECUTED",
        "raw_licensed_data_committed": False,
        "production_sha_match": f"{len(production)}/{len(CONTRACT['production_sha256'])}",
        "limitations": {
            "delisted_issue_population": "complete population is not guaranteed",
            "listing_history": "first observed bar proxy",
            "corporate_group": "unavailable; no substitute",
            "special_treatment_history": "unavailable; positive-bar proxy only",
            "trading_unit_history": "unavailable; round-lot execution is not proven",
            "ticker_lineage": "unavailable; no stitching",
            "known_at": "unavailable",
            "corporate_actions": "provider adjusted series is not comprehensive and excludes dividends",
        },
    }
    summary["u15_raw_minus_static_diagnostic"] = {
        "cagr_delta": (
            universe_summary["U15_RAW_COMMON_PERIOD"]["primary"]["cagr"]
            - universe_summary["U15_ADJUSTED_STATIC"]["primary"]["cagr"]
        ),
        "maximum_drawdown_delta": (
            universe_summary["U15_RAW_COMMON_PERIOD"]["primary"][
                "maximum_drawdown"
            ]
            - universe_summary["U15_ADJUSTED_STATIC"]["primary"][
                "maximum_drawdown"
            ]
        ),
        "purpose": "corporate_action_distortion_diagnostic_only",
    }

    aggregate_counts = read_private_json(
        run_directory / "universe_membership" / "aggregate_counts.json"
    )
    static_hash = canonical_sha256(sorted(membership["U15_ADJUSTED_STATIC"]))
    annual_rows: list[dict[str, Any]] = []
    dynamic_lookup = {
        (row["universe_id"], int(row["year"])): row for row in aggregate_counts
    }
    for schedule in schedules:
        for universe_id in ("U15_ADJUSTED_STATIC", "U15_RAW_COMMON_PERIOD"):
            annual_rows.append(
                _label(
                    {
                        "universe_id": universe_id,
                        "year": schedule.year,
                        "selection_date": schedule.selection_date,
                        "cutoff_date": schedule.cutoff_date,
                        "target_count": 15,
                        "eligible_count_lower_bound": 15,
                        "eligible_count_is_complete": True,
                        "evaluated_frontier_count": 15,
                        "selected_count": 15,
                        "shortfall_count": 0,
                        "sector_count": None,
                        "top_sector_member_share": None,
                        "sector_member_hhi": None,
                        "composition_sha256": static_hash,
                    },
                    run_id,
                )
            )
        for universe_id in ("U50_PIT_LITE", "U100_PIT_LITE"):
            row = dict(dynamic_lookup[(universe_id, schedule.year)])
            row.pop("trailing_60_start", None)
            row.pop("trailing_252_start", None)
            annual_rows.append(_label(row, run_id))

    request_summary = {
        "schema_version": "1.0",
        "run_id": run_id,
        "gate_id": GATE_ID,
        "model_id": MODEL_ID,
        "base_commit": BASE_COMMIT,
        "classification": CLASSIFICATION,
        "filevault_gate_passed_before_acquisition": True,
        "filevault_active_at_comparison": filevault_active_now,
        "private_root_outside_repository": True,
        "private_directory_mode_0700": True,
        "private_file_mode_0600": True,
        "attempts_used": request_private["attempts_used"],
        "external_prior_attempts": request_private.get(
            "external_prior_attempts", 0
        ),
        "gate_attempts_used": request_private.get(
            "gate_attempts_used", request_private["attempts_used"]
        ),
        "absolute_gate_attempt_limit": absolute_attempt_limit,
        "run_remaining_attempt_limit": request_private["hard_attempt_limit"],
        "estimated_expected_attempts": request_private["estimated_expected_attempts"],
        "planned_worst_case_attempts": request_private[
            "planned_worst_case_attempts"
        ],
        "rank_method": request_private["rank_method"],
        "endpoint_attempt_counts": request_private["endpoint_attempt_counts"],
        "http_status_counts": request_private["http_status_counts"],
        "cache_hits": request_private["cache_hits"],
        "single_threaded": True,
        "implicit_retries": 0,
        "credential_recorded": False,
        "raw_licensed_data_committed": False,
    }
    fingerprints = {
        "schema_version": "1.0",
        "run_id": run_id,
        "gate_id": GATE_ID,
        "model_id": MODEL_ID,
        "base_commit": BASE_COMMIT,
        "classification": CLASSIFICATION,
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "implementation_bundle_sha256": _implementation_hash(),
        "private_normalized_category_bundle_sha256": _private_bundle_hash(
            run_directory, "normalized"
        ),
        "private_membership_category_bundle_sha256": _private_bundle_hash(
            run_directory, "universe_membership"
        ),
        "private_ledger_category_bundle_sha256": _private_bundle_hash(
            run_directory, "trade_ledger"
        ),
        "production_sha_match_count": len(production),
        "production_sha_expected_count": len(CONTRACT["production_sha256"]),
        "aggregate_universe_year_row_count": len(annual_rows),
        "aggregate_year_metric_row_count": len(yearly_rows),
        "aggregate_split_metric_row_count": len(split_rows),
        "aggregate_score_bucket_row_count": len(score_rows),
        "raw_licensed_data_committed": False,
    }

    write_json(RESULTS_ROOT / "metrics_summary.json", summary)
    write_csv(RESULTS_ROOT / "yearly_metrics.csv", yearly_rows)
    write_csv(RESULTS_ROOT / "split_metrics.csv", split_rows)
    write_csv(RESULTS_ROOT / "score_bucket_metrics.csv", score_rows)
    write_csv(RESULTS_ROOT / "cost_sensitivity.csv", cost_rows)
    write_csv(RESULTS_ROOT / "concentration_metrics.csv", concentration)
    write_csv(RESULTS_ROOT / "universe_annual_counts.csv", annual_rows)
    write_json(RESULTS_ROOT / "data_fingerprints.json", fingerprints)
    write_json(RESULTS_ROOT / "request_audit_summary.json", request_summary)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        _build_report(
            summary,
            split_rows=split_rows,
            concentration=concentration,
            cost_rows=cost_rows,
            annual_rows=annual_rows,
            request_summary=request_summary,
        ),
        encoding="utf-8",
    )
    build_deletion_manifest(run_id, run_directory)
    return {
        "run_id": run_id,
        "effective_start": effective_start.date().isoformat(),
        "frozen_end": evaluation_end.date().isoformat(),
        "session_count": len(evaluation_sessions),
        "economic_gate": {
            "verdict": gate["verdict"],
            "universes": {
                key: value["verdict"]
                for key, value in gate["universes"].items()
            },
        },
        "production_sha_match": summary["production_sha_match"],
        "private_cleanup": "NOT_EXECUTED",
    }
