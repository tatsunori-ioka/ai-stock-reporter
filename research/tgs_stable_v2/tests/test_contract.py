from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

from tgs_stable_v2.config import (
    BASE_COMMIT,
    MAX_HOLDING_DAYS,
    SCORE_THRESHOLD,
    SCORE_WEIGHTS,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
)


LAB_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LAB_ROOT.parents[1]
CONTRACT = json.loads(
    (LAB_ROOT / "contracts" / "ver1_baseline_contract.json").read_text(encoding="utf-8")
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_frozen_constants_match_contract() -> None:
    assert CONTRACT["repository_base_commit"] == BASE_COMMIT
    assert CONTRACT["score"]["threshold"] == SCORE_THRESHOLD == 90
    assert CONTRACT["score"]["weights"] == SCORE_WEIGHTS
    assert CONTRACT["trade_rules"]["stop_loss_pct"] == STOP_LOSS_PCT == -0.10
    assert CONTRACT["trade_rules"]["take_profit_pct"] == TAKE_PROFIT_PCT == 0.30
    assert CONTRACT["trade_rules"]["maximum_holding_sessions"] == MAX_HOLDING_DAYS == 60


def test_u15_is_exact_and_unique() -> None:
    expected = [
        "6273.T",
        "6301.T",
        "6367.T",
        "7011.T",
        "5801.T",
        "5802.T",
        "5803.T",
        "8801.T",
        "8802.T",
        "8001.T",
        "8002.T",
        "8015.T",
        "8031.T",
        "8053.T",
        "8058.T",
    ]
    assert CONTRACT["universe"]["tickers"] == expected
    assert len(set(expected)) == 15


def test_production_files_match_frozen_sha256() -> None:
    for relative, expected in CONTRACT["production_sha256"].items():
        assert file_sha256(REPO_ROOT / relative) == expected


def test_u50_u100_proposals_match_pre_result_sha256() -> None:
    for relative, expected in CONTRACT["universe_proposals_sha256"].items():
        assert file_sha256(LAB_ROOT / relative) == expected


def test_110_score_is_structurally_unreachable() -> None:
    keys = list(SCORE_WEIGHTS)
    reachable: set[int] = set()
    for flags in itertools.product([False, True], repeat=len(keys)):
        values = dict(zip(keys, flags))
        # Frozen definition: a weekly MACD golden cross necessarily implies
        # MACD > signal on the same weekly bar.
        if values["weekly_macd_gc"] and not values["weekly_macd_uptrend"]:
            continue
        reachable.add(sum(SCORE_WEIGHTS[key] for key, value in values.items() if value))
    assert 90 in reachable
    assert 100 in reachable
    assert 110 not in reachable
    assert 120 in reachable
