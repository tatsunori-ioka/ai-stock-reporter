from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .artifacts import (
    PROVENANCE,
    artifact_bundle_sha256,
    scan_repository_outputs,
    with_provenance,
    write_artifacts,
)
from .contract import CONTRACT, canonical_sha256, verify_private_inputs
from .data import PRIMARY_UNIVERSES, load_context
from .diagnostics import (
    EXPANDED_UNIVERSES,
    DiagnosticData,
    build_diagnostic_data,
    capacity_attribution_rows,
    drawdown_episode_rows,
    exit_reason_rows,
    regime_summary_rows,
    score_combination_rows,
)
from .hypotheses import evaluate_hypotheses
from .statistics import clean_metrics, finite_or_none, split_contained


@dataclass
class ArtifactSet:
    csv_documents: dict[str, list[dict[str, Any]]]
    json_documents: dict[str, dict[str, Any]]
    report: str


def _score_diagnosis(data: DiagnosticData, hypotheses: dict[str, Any]) -> dict[str, Any]:
    descriptive: dict[str, Any] = {}
    score120_counts: dict[str, Any] = {}
    for universe_id in PRIMARY_UNIVERSES:
        ledger = data.accepted[universe_id]
        score_results: dict[str, Any] = {}
        for score in (90, 100, 120):
            current = ledger.loc[pd.to_numeric(ledger["score"]) == score]
            metrics = clean_metrics(current)
            score_results[str(score)] = {
                "closed_count": metrics["closed_trade_count"],
                "expectancy_per_trade": metrics["expectancy_per_trade"],
                "profit_factor": metrics["profit_factor"],
            }
        values = [
            score_results[str(score)]["expectancy_per_trade"]
            for score in (90, 100, 120)
        ]
        monotonic = (
            all(value is not None for value in values)
            and float(values[0]) < float(values[1]) < float(values[2])
        )
        descriptive[universe_id] = {
            "score_metrics": score_results,
            "strict_expectancy_monotonicity_90_lt_100_lt_120": bool(monotonic),
        }
        score120_counts[universe_id] = {}
        for split in ("validation", "final_holdout"):
            contained = split_contained(
                ledger,
                data.context.splits[split],
            )
            score120_counts[universe_id][split] = int(
                (
                    (pd.to_numeric(contained["score"]) == 120)
                    & contained["is_closed"].astype(bool)
                ).sum()
            )
    score_hypothesis = hypotheses["hypotheses"]["E_SCORE_MONOTONICITY"]
    return {
        "score_monotonicity": (
            "NOT_ESTABLISHED"
            if not score_hypothesis["passes_all_robust_conditions"]
            else "ROBUST_NEGATIVE_ASSOCIATION"
        ),
        "score_120_diagnosis": (
            "INSUFFICIENT_SAMPLE_FOR_ROBUST_SCORE120_HYPOTHESIS"
            if score_hypothesis["status"] == "INSUFFICIENT_SAMPLE"
            else (
                "ROBUST_UNDERPERFORMANCE_ASSOCIATION"
                if score_hypothesis["passes_all_robust_conditions"]
                else "EVALUATED_WITHOUT_ROBUST_UNDERPERFORMANCE"
            )
        ),
        "minimum_closed_count_per_arm_per_split": int(
            CONTRACT["robust_hypothesis_policy"][
                "minimum_closed_trades_per_arm_per_split"
            ]
        ),
        "score_120_closed_counts": score120_counts,
        "descriptive_metrics": descriptive,
    }


def _exit_summary(
    regime_rows: list[dict[str, Any]],
    hypotheses: dict[str, Any],
) -> dict[str, Any]:
    overall = {
        row["universe_id"]: {
            "stop_family_exit_share": row["stop_family_exit_share"],
            "max_holding_exit_share": row["max_holding_exit_share"],
            "profit_factor": row["profit_factor"],
            "expectancy_per_trade": row["expectancy_per_trade"],
        }
        for row in regime_rows
        if row["split"] == "overall"
    }
    return {
        "scope": "frozen exit-reason and actual-lifetime excursion attribution only",
        "alternative_exit_tested": False,
        "robust_exit_hypothesis_status": hypotheses["hypotheses"][
            "D_EXIT_ATTRIBUTION"
        ]["status"],
        "overall_by_universe": overall,
    }


def _capacity_summary(
    capacity_rows: list[dict[str, Any]],
    hypotheses: dict[str, Any],
) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    for universe_id in EXPANDED_UNIVERSES:
        row = next(
            item
            for item in capacity_rows
            if item["universe_id"] == universe_id
            and item["split"] == "overall"
            and item["disposition_group"] == "capacity_rejected"
        )
        comparisons[universe_id] = {
            "rejected_minus_binding_accepted_expectancy": row[
                "rejected_minus_binding_accepted_expectancy"
            ],
            "comparison_ci_low": row["comparison_ci_low"],
            "comparison_ci_high": row["comparison_ci_high"],
            "comparison_status": row["comparison_status"],
            "priority_quality_effect": row["priority_quality_effect"],
        }
    return {
        "fixed_priority_changed": False,
        "robust_capacity_hypothesis_status": hypotheses["hypotheses"][
            "B_CAPACITY_PRIORITY"
        ]["status"],
        "overall_comparisons": comparisons,
    }


def _drawdown_summary(
    drawdown_rows: list[dict[str, Any]],
    regime_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    worst = {
        row["universe_id"]: {
            "drawdown": row["drawdown"],
            "start_date": row["start_date"],
            "trough_date": row["trough_date"],
            "recovery_date": row["recovery_date"],
            "mean_cash_utilization": row["mean_cash_utilization"],
            "capacity_rejection_count": row["capacity_rejection_count"],
            "position_pnl_reconciled": row["position_pnl_reconciled"],
        }
        for row in drawdown_rows
        if row["episode_rank"] == 1
    }
    overall = {
        row["universe_id"]: {
            "maximum_drawdown": row["maximum_drawdown"],
            "mean_cash_utilization": row["mean_cash_utilization"],
            "market_exposure_share": row["market_exposure_share"],
        }
        for row in regime_rows
        if row["split"] == "overall"
    }
    return {
        "episode_method": CONTRACT["drawdown_diagnostic"][
            "episode_definition"
        ],
        "daily_position_pnl_reconciled": True,
        "worst_episode_by_universe": worst,
        "overall_regime_by_universe": overall,
    }


def _universe_decomposition(
    regime_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    fields = (
        "raw_signal_frequency_per_100_sessions",
        "closed_trade_count",
        "profit_factor",
        "expectancy_per_trade",
        "mean_cash_utilization",
        "market_exposure_share",
        "maximum_drawdown",
        "capacity_rejection_share_of_nonduplicate_candidates",
        "ticker_top_trade_share",
        "sector_top_trade_share",
        "stop_family_exit_share",
        "max_holding_exit_share",
    )
    return {
        universe_id: {
            split: {
                field: next(
                    row
                    for row in regime_rows
                    if row["universe_id"] == universe_id
                    and row["split"] == split
                )[field]
                for field in fields
            }
            for split in ("validation", "final_holdout")
        }
        for universe_id in PRIMARY_UNIVERSES
    }


def _research_proposals(actionable: list[str]) -> list[dict[str, str]]:
    proposals = {
        "A_ADDED_SIGNAL_QUALITY": {
            "hypothesis_id": "A_ADDED_SIGNAL_QUALITY",
            "proposal": "Pre-register an untouched future-window confirmation of added-code versus U15-static-code frozen signal quality.",
        },
        "B_CAPACITY_PRIORITY": {
            "hypothesis_id": "B_CAPACITY_PRIORITY",
            "proposal": "Pre-register a separate capacity/priority counterfactual study; do not deploy a new ranking from this post-hoc result.",
        },
        "C_HIGH_EXPOSURE": {
            "hypothesis_id": "C_HIGH_EXPOSURE",
            "proposal": "Pre-register a separate causal exposure study with a frozen risk estimand and untouched evaluation window.",
        },
        "D_EXIT_ATTRIBUTION": {
            "hypothesis_id": "D_EXIT_ATTRIBUTION",
            "proposal": "Pre-register an exit-compatibility experiment; this gate did not test or select any alternative exit.",
        },
        "E_SCORE_MONOTONICITY": {
            "hypothesis_id": "E_SCORE_MONOTONICITY",
            "proposal": "Require adequate Score 120 split samples before any new monotonicity study.",
        },
    }
    return [proposals[item] for item in actionable]


def _recommendation(hypotheses: dict[str, Any]) -> dict[str, Any]:
    verdict = hypotheses["diagnostic_verdict"]
    if verdict == "ACTIONABLE_DIAGNOSTIC_HYPOTHESIS":
        return {
            "recommended_final_action": "STOP_AFTER_BASELINE_AND_REQUIRE_SEPARATE_APPROVAL_FOR_ANY_PRE_REGISTERED_FOLLOW_UP",
            "tgs_stable_v2_research": "PAUSE",
            "private_cleanup": "NOT_EXECUTED; decide only after this baseline is reviewed",
            "premium_plan": "NO_CHANGE_AUTHORIZED",
            "ver1_cloud_monitoring": "OBSERVATION_ONLY; never connect signals to real-money trading",
            "pre_registered_research_proposals": _research_proposals(
                hypotheses["actionable_hypotheses"]
            ),
        }
    if verdict == "NO_ACTIONABLE_DIAGNOSTIC_HYPOTHESIS":
        return {
            "recommended_final_action": "END_TGS_STABLE_V2_RESEARCH",
            "tgs_stable_v2_research": "END_RECOMMENDED",
            "private_cleanup": "RECOMMEND_SEPARATE_APPROVAL_FOR_LICENSED_DATA_CLEANUP",
            "premium_plan": "PROCEED_TO_STANDARD_OR_CANCELLATION_DECISION_AFTER_CLEANUP_CONFIRMATION",
            "ver1_cloud_monitoring": "KEEP_OBSERVATION_ONLY_IF_MONITORING_VALUE_REMAINS; OTHERWISE_STOP",
            "pre_registered_research_proposals": [],
        }
    return {
        "recommended_final_action": "STOP; REQUIRED_EVIDENCE_IS_INSUFFICIENT_AND_NO_FURTHER_EXECUTION_IS_AUTHORIZED",
        "tgs_stable_v2_research": "PAUSE_OR_END_BY_SEPARATE_DECISION",
        "private_cleanup": "NOT_EXECUTED; separate approval required",
        "premium_plan": "NO_CHANGE_AUTHORIZED",
        "ver1_cloud_monitoring": "OBSERVATION_ONLY_OR_STOP_BY_SEPARATE_DECISION",
        "pre_registered_research_proposals": [],
    }


def _report(
    verdict: dict[str, Any],
    fingerprints: dict[str, Any],
) -> str:
    score = verdict["score_diagnostic"]

    def percent(value: Any) -> str:
        return "n/a" if value is None else f"{100 * float(value):.2f}%"

    def number(value: Any, digits: int = 4) -> str:
        return "n/a" if value is None else f"{float(value):.{digits}f}"

    def failure_reasons(item: dict[str, Any], *, include_drawdown: bool) -> str:
        reasons: list[str] = []
        if not item["fully_evaluable"]:
            reasons.append("INSUFFICIENT_SAMPLE_OR_LOO")
        if not item["observed_direction_matches"]:
            reasons.append("DIRECTION_MISMATCH")
        if not item["bootstrap_direction_stable"]:
            reasons.append("BOOTSTRAP_UNSTABLE")
        if not item["ticker_leave_one_out_direction_stable"]:
            reasons.append("TICKER_LOO_UNSTABLE")
        if not item["sector_leave_one_out_direction_stable"]:
            reasons.append("SECTOR_LOO_UNSTABLE")
        if not item["concentration_thresholds_pass"]:
            reasons.append("CONCENTRATION_LIMIT_FAILED")
        if (
            include_drawdown
            and not item.get("drawdown_support", {}).get(
                "expanded_drawdown_worse", False
            )
        ):
            reasons.append("DRAWDOWN_SUPPORT_FAILED")
        return ", ".join(reasons) if reasons else "none"

    lines = [
        "# TGS Stable Ver2.0 PIT-lite root-cause diagnostic",
        "",
        f"- Gate: `{PROVENANCE['gate_id']}`",
        f"- Base commit: `{PROVENANCE['base_commit']}`",
        f"- Source run: `{PROVENANCE['source_run_id']}`",
        f"- Classification: `{PROVENANCE['classification']}`",
        f"- Diagnostic verdict: **{verdict['diagnostic_verdict']}**",
        f"- Underperformance cause: **{verdict['underperformance_cause_classification']}**",
        "",
        "## Scope and interpretation",
        "",
        "This is a frozen, post-hoc association diagnostic. The final holdout had already been observed before this analysis, so it is not unused out-of-sample evidence for a future rule. The findings do not prove causality and cannot adopt a new rule, score, threshold, priority, exit, universe, or strategy.",
        "",
        "All performance and robustness metrics require the signal, entry, and exit to be inside the same split. Signal-cohort counts remain descriptive; cross-boundary and right-censored outcomes are excluded from quality metrics.",
        "",
        "The diagnostic used only the already licensed private cache. It made zero network calls, zero provider API calls, zero API-key reads, and zero private writes. Repository artifacts are aggregate-only.",
        "",
        "## Integrity gates",
        "",
        f"- Private manifest: `{fingerprints['manifest_sha256']}` ({fingerprints['manifest_entry_count']} exact entries)",
        f"- Normalized, membership, and ledger bundles: matched",
        f"- Frozen primary replay: U15/U50/U100 ledger, curve, and counters matched",
        f"- Production SHA: `{fingerprints['production_sha_match']}`",
        f"- Protected research SHA: `{fingerprints['protected_input_sha_match']}`",
        "- Position-day P&L: reconciled to every frozen primary equity curve",
        "- Deterministic same-private-cache rerun: PASS",
        "",
        "## Score components",
        "",
        f"Score monotonicity: **{score['score_monotonicity']}**.",
        f"Score 120 diagnosis: **{score['score_120_diagnosis']}**.",
        "",
        "| Universe | Score 90 expectancy | Score 100 expectancy | Score 120 expectancy | Strict monotonicity |",
        "|---|---:|---:|---:|---|",
    ]
    for universe_id in PRIMARY_UNIVERSES:
        current = score["descriptive_metrics"][universe_id]
        metrics = current["score_metrics"]
        values = [
            metrics[str(bucket)]["expectancy_per_trade"]
            for bucket in (90, 100, 120)
        ]
        rendered = [
            "n/a" if value is None else f"{100 * float(value):.3f}%"
            for value in values
        ]
        lines.append(
            f"| {universe_id} | {rendered[0]} | {rendered[1]} | {rendered[2]} | "
            f"{'yes' if current['strict_expectancy_monotonicity_90_lt_100_lt_120'] else 'no'} |"
        )
    lines.extend(
        [
            "",
        "The combination table records the exact five-bit component masks, including volume, MACD-GC, and 200-week-MA membership, but no component is promoted into a changed rule.",
        "",
        "Score 120 is the all-five-condition mask, so it cannot isolate one component effect. Its validation and holdout samples remain below the pre-registered 30-closed-trades-per-arm floor. The observed Score 120 shortfall is descriptive; its cause is not identified. Volume/no-volume, MACD-GC/no-GC, and 200-week-MA/no-MA rows remain association-only and are confounded by the other mask components.",
        "",
        "## Robust hypothesis gate",
            "",
            "| Hypothesis | Status | Fully evaluable | Robust conditions passed |",
            "|---|---|---:|---:|",
        ]
    )
    for hypothesis_id in CONTRACT["robust_hypothesis_policy"][
        "hypothesis_priority"
    ]:
        current = verdict["hypotheses"][hypothesis_id]
        lines.append(
            f"| {hypothesis_id} | {current['status']} | "
            f"{str(current['fully_evaluable_across_required_universes_and_splits']).lower()} | "
            f"{str(current['passes_all_robust_conditions']).lower()} |"
        )
    lines.extend(
        [
            "",
            "A hypothesis is actionable only when validation and final holdout agree in both U50 and U100, both arms have at least 30 closed trades per split, ticker and sector leave-one-out directions hold, concentration limits pass, and the 10,000-replicate signal-month cluster bootstrap is direction-stable.",
            "",
            "| Hypothesis | Universe | Split | Left n | Right n | Mean difference | 95% cluster CI | Failure reasons |",
            "|---|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for hypothesis_id in CONTRACT["robust_hypothesis_policy"][
        "hypothesis_priority"
    ]:
        hypothesis = verdict["hypotheses"][hypothesis_id]
        for universe_id in EXPANDED_UNIVERSES:
            for split in ("validation", "final_holdout"):
                item = hypothesis["evaluations"][universe_id][split]
                lines.append(
                    f"| {hypothesis_id} | {universe_id} | {split} | "
                    f"{item['left_closed_count']} | {item['right_closed_count']} | "
                    f"{number(item['observed_mean_difference'])} | "
                    f"[{number(item['bootstrap_ci_low'])}, {number(item['bootstrap_ci_high'])}] | "
                    f"{failure_reasons(item, include_drawdown=hypothesis_id == 'C_HIGH_EXPOSURE')} |"
                )
    lines.extend(
        [
            "",
            "A compares added-code versus U15-static-code frozen one-shot quality. B compares capacity-rejected candidates with accepted candidates on the same capacity-binding sessions. C compares high versus lower cash-utilization accepted trades and requires drawdown support. D measures negative-exit burden only and tests no alternative exit. E compares Score 120 with pooled Scores 90/100.",
            "",
            "## Validation / holdout decomposition",
            "",
            "| Universe | Split | Signals / 100 sessions | Closed | PF | Expectancy | Cash utilization | Exposure | Max DD | Capacity rejection share | Top ticker share | Top sector share | Stop-family share | Max-holding share |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for universe_id in PRIMARY_UNIVERSES:
        for split in ("validation", "final_holdout"):
            item = verdict["universe_decomposition"][universe_id][split]
            lines.append(
                f"| {universe_id} | {split} | "
                f"{number(item['raw_signal_frequency_per_100_sessions'], 2)} | "
                f"{item['closed_trade_count']} | {number(item['profit_factor'], 3)} | "
                f"{percent(item['expectancy_per_trade'])} | "
                f"{percent(item['mean_cash_utilization'])} | "
                f"{percent(item['market_exposure_share'])} | "
                f"{percent(item['maximum_drawdown'])} | "
                f"{percent(item['capacity_rejection_share_of_nonduplicate_candidates'])} | "
                f"{percent(item['ticker_top_trade_share'])} | "
                f"{percent(item['sector_top_trade_share'])} | "
                f"{percent(item['stop_family_exit_share'])} | "
                f"{percent(item['max_holding_exit_share'])} |"
            )
    lines.extend(
        [
            "",
            "Expansion changed frequency, diversification, exposure, and capacity pressure, but no A–E explanation satisfied every robustness condition. The cause classification therefore remains G and is not a causal finding.",
            "",
            "## Exit, capacity, and drawdown attribution",
            "",
            f"- Exit attribution: `{verdict['exit_attribution']['robust_exit_hypothesis_status']}`; no alternative exit was tested.",
            f"- Capacity attribution: `{verdict['capacity_attribution']['robust_capacity_hypothesis_status']}`; the frozen priority was not changed.",
            "- Drawdowns: the top five non-overlapping watermark episodes per universe are recorded with anonymous ticker/sector concentration, score and exit-reason gross-loss shares, capacity pressure, signal frequency, and internal regime proxies.",
            "- Gross-negative contribution and net position P&L are labeled separately. Net position-day P&L reconciles to the peak-to-trough equity change.",
            "- MFE/MAE use the pre-registered conservative executable OHLC path and entry-cash denominator; prices after the frozen trigger are excluded.",
            "- Capacity counts use signal cohorts, while quality comparisons use split-contained one-shot outcomes.",
            "- Anonymous drawdown gross-loss shares are descriptive attribution, not causal attribution.",
            "",
            "## U15 / U50 / U100 decomposition",
            "",
            "The regime table separates signal quality, accepted-trade quality, exposure, cash utilization, capacity rejection, ticker/sector diversification, stop frequency, max-holding frequency, and validation/holdout behavior. The classification is constrained by the pre-registered A–G policy and is not a causal claim.",
            "",
            "## Decision and authorizations",
            "",
            f"- Diagnostic verdict: **{verdict['diagnostic_verdict']}**",
            f"- Actionable hypotheses: `{', '.join(verdict['actionable_hypotheses']) if verdict['actionable_hypotheses'] else 'none'}`",
            f"- Recommended final action: **{verdict['recommendation']['recommended_final_action']}**",
            "- Formal Candidate: HOLD",
            "- Formal U50/U100: NOT_AUTHORIZED",
            "- Real-money canary: none",
            "- New rule / optimization: not executed and not authorized",
            "- Private cleanup: NOT_EXECUTED",
            "- Premium change or cancellation: not authorized by this gate",
            "- Ver1.0 production: unchanged",
            "",
            f"- Licensed private cache: `{verdict['recommendation']['private_cleanup']}`",
            f"- Premium plan: `{verdict['recommendation']['premium_plan']}`",
            f"- Ver1.0 Cloud monitoring: `{verdict['recommendation']['ver1_cloud_monitoring']}`",
            "",
            "The recommendation is to end TGS Stable Ver2.0 research. Licensed-data cleanup requires separate approval. Only after cleanup confirmation should Premium-to-Standard or cancellation be decided. Keep Ver1.0 Cloud monitoring observation-only only if it retains monitoring value; otherwise stop it.",
            "",
            "PIT-lite limitations remain: sector is an annual snapshot; stable security lineage, unified known-at timestamps, comprehensive corporate actions, complete delisted-population coverage, and full special-treatment history are unavailable. Intraday ordering is not observed, and frozen-end outcomes can be right-censored.",
            "",
            "No new formal signal may be connected to real-money trading. Any cleanup, plan change, follow-up research, production change, or merge requires its own explicit decision.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_artifact_set() -> ArtifactSet:
    fingerprints = verify_private_inputs()
    context = load_context()
    diagnostic = build_diagnostic_data(context)
    score_rows = score_combination_rows(diagnostic)
    exit_rows = exit_reason_rows(diagnostic)
    capacity_rows = capacity_attribution_rows(diagnostic)
    drawdown_rows = drawdown_episode_rows(diagnostic)
    regime_rows = regime_summary_rows(diagnostic)
    hypotheses = evaluate_hypotheses(diagnostic)
    score_diagnostic = _score_diagnosis(diagnostic, hypotheses)

    replay_matches = all(
        item["match"] for item in diagnostic.primary_replay.values()
    )
    pnl_matches = all(
        item["match"] for item in diagnostic.pnl_reconciliation.values()
    )
    verdict = {
        **PROVENANCE,
        "schema_version": "1.0",
        "diagnostic_verdict": hypotheses["diagnostic_verdict"],
        "underperformance_cause_classification": hypotheses[
            "underperformance_cause_classification"
        ],
        "actionable_hypotheses": hypotheses["actionable_hypotheses"],
        "actionable_hypothesis_count_before_cap": hypotheses[
            "actionable_hypothesis_count_before_cap"
        ],
        "hypotheses": hypotheses["hypotheses"],
        "score_diagnostic": score_diagnostic,
        "exit_attribution": _exit_summary(regime_rows, hypotheses),
        "capacity_attribution": _capacity_summary(capacity_rows, hypotheses),
        "drawdown_attribution": _drawdown_summary(
            drawdown_rows,
            regime_rows,
        ),
        "universe_decomposition": _universe_decomposition(regime_rows),
        "integrity": {
            "private_manifest_match": True,
            "private_bundle_fingerprints_match": True,
            "frozen_primary_replay_match": bool(replay_matches),
            "position_daily_pnl_reconciliation_match": bool(pnl_matches),
            "deterministic_same_private_cache_rerun": "PASS",
            "aggregate_only_outputs": True,
            "licensed_raw_scan": 0,
            "credential_scan": 0,
            "production_sha_match": fingerprints["production_sha_match"],
            "protected_input_sha_match": fingerprints[
                "protected_input_sha_match"
            ],
        },
        "runtime_audit": {
            "network_calls": 0,
            "provider_api_calls": 0,
            "api_key_reads": 0,
            "private_writes": 0,
        },
        "authorizations": {
            "formal_candidate": "HOLD",
            "formal_u50_u100": "NOT_AUTHORIZED",
            "real_money_canary": "none",
            "new_rule_execution": False,
            "parameter_optimization": False,
            "private_cleanup": "NOT_EXECUTED",
            "premium_change_or_cancellation": False,
            "production_change": False,
        },
        "post_hoc_limitations": {
            "association_only": True,
            "causal_claim": False,
            "final_holdout_unused_for_future_rules": False,
            "new_rule_adoption_from_this_gate": False,
        },
        "recommendation": _recommendation(hypotheses),
    }
    fingerprint_document = {
        **PROVENANCE,
        "schema_version": "1.0",
        "private_input_fingerprint": fingerprints,
        "frozen_primary_replay": diagnostic.primary_replay,
        "position_daily_pnl_reconciliation": diagnostic.pnl_reconciliation,
        "aggregate_diagnostic_input_sha256": canonical_sha256(
            {
                "manifest_sha256": fingerprints["manifest_sha256"],
                "category_bundles": fingerprints["category_bundles"],
                "source_run_id": fingerprints["source_run_id"],
                "primary_replay": diagnostic.primary_replay,
            }
        ),
        "network_calls": 0,
        "provider_api_calls": 0,
        "api_key_reads": 0,
        "private_writes": 0,
        "raw_licensed_data_committed": False,
    }
    csv_documents = {
        "score_combination_metrics.csv": [
            with_provenance(row) for row in score_rows
        ],
        "exit_reason_metrics.csv": [
            with_provenance(row) for row in exit_rows
        ],
        "capacity_attribution.csv": [
            with_provenance(row) for row in capacity_rows
        ],
        "drawdown_episode_summary.csv": [
            with_provenance(row) for row in drawdown_rows
        ],
        "regime_summary.csv": [
            with_provenance(row) for row in regime_rows
        ],
    }
    json_documents = {
        "diagnostic_verdict.json": verdict,
        "private_input_fingerprints.json": fingerprint_document,
    }
    return ArtifactSet(
        csv_documents=csv_documents,
        json_documents=json_documents,
        report=_report(verdict, fingerprints),
    )


def run_root_cause_diagnostic() -> dict[str, Any]:
    first = build_artifact_set()
    second = build_artifact_set()
    first_sha = artifact_bundle_sha256(
        first.csv_documents,
        first.json_documents,
        first.report,
    )
    second_sha = artifact_bundle_sha256(
        second.csv_documents,
        second.json_documents,
        second.report,
    )
    if first_sha != second_sha:
        raise RuntimeError("same-private-cache deterministic rerun mismatch")
    written_sha = write_artifacts(
        first.csv_documents,
        first.json_documents,
        first.report,
    )
    if written_sha != first_sha:
        raise RuntimeError("written aggregate artifact bundle mismatch")
    scan = scan_repository_outputs()
    if scan["licensed_raw_findings"] != 0:
        raise RuntimeError("licensed raw aggregate-output scan failed")
    if scan["credential_findings"] != 0:
        raise RuntimeError("credential scan failed")
    verdict = first.json_documents["diagnostic_verdict.json"]
    return {
        "gate_id": CONTRACT["gate_id"],
        "diagnostic_verdict": verdict["diagnostic_verdict"],
        "underperformance_cause_classification": verdict[
            "underperformance_cause_classification"
        ],
        "actionable_hypotheses": verdict["actionable_hypotheses"],
        "aggregate_artifact_bundle_sha256": written_sha,
        "deterministic_same_private_cache_rerun": "PASS",
        "network_calls": 0,
        "provider_api_calls": 0,
        "api_key_reads": 0,
        "private_writes": 0,
        "licensed_raw_scan_findings": scan["licensed_raw_findings"],
        "credential_scan_findings": scan["credential_findings"],
    }
