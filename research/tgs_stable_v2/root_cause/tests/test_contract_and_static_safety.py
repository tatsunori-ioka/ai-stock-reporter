from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from root_cause.contract import (
    CONTRACT,
    PRIVATE_ROOT,
    REPOSITORY_ROOT,
    sha256_file,
)


ROOT_CAUSE_ROOT = Path(__file__).resolve().parents[1]


def test_contract_identity_is_frozen_to_pr10_merge() -> None:
    assert CONTRACT["gate_id"] == "V2-R2B_ROOT_CAUSE_DIAGNOSTIC_AND_STOP_DECISION"
    assert CONTRACT["base_commit"] == "9dae034999aa33b3f0d059adc059d3c8dbe659c2"
    assert CONTRACT["source_run_id"] == "v2-r2a-20260727-d3b8ed0-integrity1"
    assert CONTRACT["classification"] == "POST_HOC_ASSOCIATION_DIAGNOSTIC_ONLY"


def test_private_root_is_outside_repository() -> None:
    private = PRIVATE_ROOT.expanduser().resolve()
    repository = REPOSITORY_ROOT.resolve()
    assert private != repository
    assert repository not in private.parents


def test_rules_are_the_frozen_ver1_rules() -> None:
    rules = CONTRACT["rules"]
    assert rules["score_threshold"] == 90
    assert rules["stop_loss_pct"] == pytest.approx(-0.10)
    assert rules["take_profit_pct"] == pytest.approx(0.30)
    assert rules["maximum_holding_ticker_sessions"] == 60
    assert rules["maximum_positions"] == 10
    assert rules["maximum_position_fraction"] == pytest.approx(0.10)
    assert rules["universe_reselection"] is False
    assert rules["new_rule_execution"] is False
    assert rules["parameter_search"] is False


def test_score_bitmasks_have_the_expected_frozen_scores() -> None:
    values = CONTRACT["score_bitmask"]["bit_values"]
    weights = CONTRACT["score_bitmask"]["score_weights"]

    def score(mask: int) -> int:
        return sum(
            weights[name]
            for name, bit in values.items()
            if mask & int(bit)
        )

    assert {mask: score(mask) for mask in (29, 30)} == {29: 90, 30: 90}
    assert {mask: score(mask) for mask in (15, 23)} == {15: 100, 23: 100}
    assert score(31) == 120
    assert 110 not in {score(mask) for mask in range(32)}


def test_split_and_post_hoc_policies_are_explicit() -> None:
    assert CONTRACT["split_policy"]["development_fraction"] == pytest.approx(0.60)
    assert CONTRACT["split_policy"]["validation_fraction"] == pytest.approx(0.20)
    assert CONTRACT["split_policy"]["final_holdout_fraction"] == pytest.approx(0.20)
    policy = CONTRACT["robust_hypothesis_policy"]
    assert policy["post_hoc"] is True
    assert policy["causal_claim"] is False
    assert policy["final_holdout_is_unused_oos_for_future_rules"] is False
    assert policy["minimum_closed_trades_per_arm_per_split"] == 30
    assert policy["cluster_bootstrap"]["replicates"] == 10_000


def test_all_five_hypothesis_estimands_are_predeclared() -> None:
    expected = set(CONTRACT["robust_hypothesis_policy"]["hypothesis_priority"])
    estimands = CONTRACT["diagnostic_hypothesis_estimands"]
    assert expected <= set(estimands)
    assert estimands["C_HIGH_EXPOSURE"]["high_exposure_threshold"] == pytest.approx(
        0.8
    )
    assert estimands["D_EXIT_ATTRIBUTION"]["scope"].startswith("association only")


def test_final_authorizations_remain_closed() -> None:
    authorizations = CONTRACT["authorizations"]
    assert authorizations["formal_candidate_promotion"] is False
    assert authorizations["formal_u50_u100"] == "NOT_AUTHORIZED"
    assert authorizations["real_money_canary"] == "none"
    assert authorizations["new_rule_execution"] is False
    assert authorizations["parameter_optimization"] is False
    assert authorizations["private_data_cleanup"] == "NOT_EXECUTED"
    assert authorizations["production_change"] is False


def test_repository_result_allowlist_is_exact() -> None:
    assert set(CONTRACT["repository_output_policy"]["allowed_results"]) == {
        "score_combination_metrics.csv",
        "exit_reason_metrics.csv",
        "capacity_attribution.csv",
        "drawdown_episode_summary.csv",
        "regime_summary.csv",
        "diagnostic_verdict.json",
        "private_input_fingerprints.json",
    }


def test_private_analytical_allowlist_excludes_raw_and_request_bodies() -> None:
    allowed = CONTRACT["private_input"]["allowed_analytical_categories"]
    forbidden = CONTRACT["private_input"]["forbidden_after_fingerprint_gate"]
    assert not any(value.startswith("raw") for value in allowed)
    assert "raw" in forbidden
    assert "normalized/request_cache" in forbidden
    assert "normalized/rank_discovery.json" in forbidden


@pytest.mark.parametrize(
    "mapping_name",
    (
        "upstream_research_sha256",
        "pit_protected_inputs_sha256",
        "production_sha256",
    ),
)
def test_public_repository_fingerprints_match(mapping_name: str) -> None:
    mapping = CONTRACT[mapping_name]
    assert mapping
    for relative, expected in mapping.items():
        assert sha256_file(REPOSITORY_ROOT / relative) == expected


def test_expected_public_fingerprint_counts_are_frozen() -> None:
    assert len(CONTRACT["upstream_research_sha256"]) == 6
    assert len(CONTRACT["pit_protected_inputs_sha256"]) == 6
    assert len(CONTRACT["production_sha256"]) == 19


def test_runtime_policy_declares_zero_external_access() -> None:
    runtime = CONTRACT["runtime_policy"]
    assert runtime["diagnostic_network_calls"] == 0
    assert runtime["provider_api_calls"] == 0
    assert runtime["api_key_reads"] == 0
    assert runtime["private_writes"] == 0


def test_python_sources_are_syntactically_valid() -> None:
    paths = sorted(
        [
            *ROOT_CAUSE_ROOT.joinpath("src").rglob("*.py"),
            *ROOT_CAUSE_ROOT.joinpath("scripts").rglob("*.py"),
            *ROOT_CAUSE_ROOT.joinpath("tests").rglob("*.py"),
        ]
    )
    assert paths
    for path in paths:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_diagnostic_source_does_not_import_provider_or_network_clients() -> None:
    banned = (
        "requests",
        "httpx",
        "urllib.request",
        "http.client",
        "urllib3",
        "pit_lite.api",
        "pit_lite.acquisition",
    )
    for path in sorted(ROOT_CAUSE_ROOT.joinpath("src").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for module in banned:
            assert f"import {module}" not in source
            assert f"from {module} import" not in source


def test_runner_installs_network_guard_and_never_reads_key_value() -> None:
    source = (
        ROOT_CAUSE_ROOT
        / "scripts"
        / "run_root_cause_diagnostic.py"
    ).read_text(encoding="utf-8")
    assert "_install_network_guard()" in source
    assert '"JQUANTS_API_KEY" in os.environ' in source
    assert "os.environ.get" not in source
    assert "os.getenv" not in source


def test_contract_is_valid_json_without_nonfinite_values() -> None:
    text = (
        ROOT_CAUSE_ROOT
        / "contracts"
        / "ROOT_CAUSE_DIAGNOSTIC_CONTRACT.json"
    ).read_text(encoding="utf-8")
    loaded = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(
        ValueError(value)
    ))
    assert loaded == CONTRACT
