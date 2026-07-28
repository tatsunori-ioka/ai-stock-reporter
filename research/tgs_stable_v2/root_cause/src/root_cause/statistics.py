from __future__ import annotations

import hashlib
import math
from typing import Any, Iterable

import numpy as np
import pandas as pd

from tgs_stable_v2.metrics import trade_metrics

from .contract import CONTRACT


MIN_TRADES = int(
    CONTRACT["robust_hypothesis_policy"]["minimum_closed_trades_per_arm_per_split"]
)
MIN_CLUSTERS = int(
    CONTRACT["robust_hypothesis_policy"]["minimum_signal_month_clusters"]
)
BOOTSTRAP = CONTRACT["robust_hypothesis_policy"]["cluster_bootstrap"]


def finite_or_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    return value


def clean_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    adapted = frame.copy()
    if "ticker" not in adapted and "code" in adapted:
        adapted["ticker"] = adapted["code"]
    result = {
        key: finite_or_none(value)
        for key, value in trade_metrics(adapted).items()
    }
    result["sample_status"] = (
        "SUFFICIENT"
        if int(result["closed_trade_count"]) >= MIN_TRADES
        else "INSUFFICIENT_SAMPLE"
    )
    return result


def split_contained(
    frame: pd.DataFrame,
    bounds: dict[str, pd.Timestamp],
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    start = pd.Timestamp(bounds["start"])
    end = pd.Timestamp(bounds["end"])
    signal = pd.to_datetime(frame["signal_date"])
    entry = pd.to_datetime(frame["entry_date"])
    exit_date = pd.to_datetime(frame["exit_date"])
    return frame.loc[
        (signal >= start)
        & (signal <= end)
        & (entry >= start)
        & (exit_date <= end)
    ].copy()


def signal_in_split(
    frame: pd.DataFrame,
    bounds: dict[str, pd.Timestamp],
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    signal = pd.to_datetime(frame["signal_date"])
    return frame.loc[
        (signal >= pd.Timestamp(bounds["start"]))
        & (signal <= pd.Timestamp(bounds["end"]))
    ].copy()


def concentration(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    if frame.empty:
        return {
            "distinct_bucket_count": 0,
            "top_bucket_share": None,
            "hhi": None,
        }
    counts = frame[column].fillna("").astype(str).value_counts()
    shares = counts / counts.sum()
    return {
        "distinct_bucket_count": int(len(shares)),
        "top_bucket_share": finite_or_none(shares.max()),
        "hhi": finite_or_none((shares**2).sum()),
    }


def loss_concentration(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    closed = frame.loc[frame["is_closed"].astype(bool)].copy()
    returns = pd.to_numeric(closed["net_return_pct"], errors="coerce")
    closed = closed.loc[returns < 0].copy()
    if closed.empty:
        return {
            "distinct_loss_bucket_count": 0,
            "top_loss_share": None,
            "loss_hhi": None,
        }
    closed["_loss"] = -pd.to_numeric(closed["net_return_pct"])
    losses = closed.groupby(column, dropna=False)["_loss"].sum()
    total = float(losses.sum())
    if total <= 0:
        return {
            "distinct_loss_bucket_count": int(len(losses)),
            "top_loss_share": None,
            "loss_hhi": None,
        }
    shares = losses / total
    return {
        "distinct_loss_bucket_count": int(len(shares)),
        "top_loss_share": finite_or_none(shares.max()),
        "loss_hhi": finite_or_none((shares**2).sum()),
    }


def normalize_exit_reason(reason: Any) -> str:
    value = str(reason)
    if value == "stop_loss" or value == "stop_and_take_same_day_stop_first":
        return "stop_loss"
    if value == "stop_gap":
        return "stop_gap"
    if value == "take_profit" or value == "stop_and_take_same_day_take_first":
        return "take_profit"
    if value == "take_profit_gap":
        return "take_profit_gap"
    if value == "max_holding":
        return "max_holding"
    if value.startswith("premature_data_end"):
        return "data_end_or_haircut"
    return "other"


def _seed(label: str) -> int:
    digest = hashlib.sha256(label.encode("utf-8")).digest()
    offset = int.from_bytes(digest[:8], "big")
    return (int(BOOTSTRAP["seed"]) + offset) % (2**63 - 1)


def cluster_bootstrap_difference(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    label: str,
) -> dict[str, Any]:
    return cluster_bootstrap_value_difference(
        left,
        right,
        value_column="net_return_pct",
        label=label,
    )


def cluster_bootstrap_value_difference(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    value_column: str,
    label: str,
) -> dict[str, Any]:
    def closed_monthly_sums(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["sum", "count"])
        current = frame.loc[frame["is_closed"].astype(bool)].copy()
        current["_value"] = pd.to_numeric(
            current[value_column],
            errors="coerce",
        )
        current["_month"] = pd.to_datetime(current["signal_date"]).dt.strftime(
            "%Y-%m"
        )
        current = current.dropna(subset=["_value"])
        return current.groupby("_month")["_value"].agg(["sum", "count"])

    left_closed = left.loc[left["is_closed"].astype(bool)].copy()
    right_closed = right.loc[right["is_closed"].astype(bool)].copy()
    left_returns = pd.to_numeric(
        left_closed[value_column], errors="coerce"
    ).dropna()
    right_returns = pd.to_numeric(
        right_closed[value_column], errors="coerce"
    ).dropna()
    left_monthly = closed_monthly_sums(left_closed)
    right_monthly = closed_monthly_sums(right_closed)
    clusters = sorted(set(left_monthly.index) | set(right_monthly.index))
    observed = (
        float(left_returns.mean() - right_returns.mean())
        if not left_returns.empty and not right_returns.empty
        else None
    )
    base = {
        "left_closed_trades": int(len(left_returns)),
        "right_closed_trades": int(len(right_returns)),
        "signal_month_clusters": int(len(clusters)),
        "observed_expectancy_difference": finite_or_none(observed),
    }
    if (
        base["left_closed_trades"] < MIN_TRADES
        or base["right_closed_trades"] < MIN_TRADES
        or len(clusters) < MIN_CLUSTERS
        or observed is None
        or observed == 0
    ):
        return {
            **base,
            "status": "INSUFFICIENT_SAMPLE",
            "valid_replicate_fraction": None,
            "same_direction_fraction": None,
            "ci_low": None,
            "ci_high": None,
            "direction_stable": False,
        }

    left_sums = left_monthly["sum"].reindex(clusters, fill_value=0.0).to_numpy()
    left_counts = left_monthly["count"].reindex(clusters, fill_value=0).to_numpy()
    right_sums = right_monthly["sum"].reindex(clusters, fill_value=0.0).to_numpy()
    right_counts = right_monthly["count"].reindex(clusters, fill_value=0).to_numpy()
    replicates = int(BOOTSTRAP["replicates"])
    rng = np.random.default_rng(_seed(label))
    indices = rng.integers(0, len(clusters), size=(replicates, len(clusters)))
    sampled_left_counts = left_counts[indices].sum(axis=1)
    sampled_right_counts = right_counts[indices].sum(axis=1)
    valid = (sampled_left_counts > 0) & (sampled_right_counts > 0)
    samples = (
        left_sums[indices].sum(axis=1)[valid] / sampled_left_counts[valid]
        - right_sums[indices].sum(axis=1)[valid] / sampled_right_counts[valid]
    )
    samples = samples[np.isfinite(samples)]
    valid_fraction = len(samples) / replicates
    if samples.size == 0:
        return {
            **base,
            "status": "INSUFFICIENT_SAMPLE",
            "valid_replicate_fraction": finite_or_none(valid_fraction),
            "same_direction_fraction": None,
            "ci_low": None,
            "ci_high": None,
            "direction_stable": False,
        }
    alpha = (1.0 - float(BOOTSTRAP["confidence_level"])) / 2.0
    ci_low, ci_high = np.quantile(samples, [alpha, 1.0 - alpha])
    direction = 1.0 if observed > 0 else -1.0
    same_direction = float(np.mean(np.sign(samples) == direction))
    stable = (
        valid_fraction >= float(BOOTSTRAP["minimum_valid_replicate_fraction"])
        and same_direction >= float(BOOTSTRAP["minimum_same_direction_fraction"])
        and ((ci_low > 0 and observed > 0) or (ci_high < 0 and observed < 0))
    )
    return {
        **base,
        "status": "SUFFICIENT",
        "valid_replicate_fraction": finite_or_none(valid_fraction),
        "same_direction_fraction": finite_or_none(same_direction),
        "ci_low": finite_or_none(ci_low),
        "ci_high": finite_or_none(ci_high),
        "direction_stable": bool(stable),
    }


def leave_one_bucket_out(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    column: str,
    expected_sign: int,
    value_column: str = "net_return_pct",
) -> dict[str, Any]:
    buckets = sorted(
        set(left[column].fillna("").astype(str))
        | set(right[column].fillna("").astype(str))
    )
    effects: list[float] = []
    stable = 0
    evaluable = 0
    for bucket in buckets:
        left_current = left.loc[left[column].fillna("").astype(str) != bucket]
        right_current = right.loc[right[column].fillna("").astype(str) != bucket]
        left_returns = pd.to_numeric(
            left_current.loc[
                left_current["is_closed"].astype(bool),
                value_column,
            ],
            errors="coerce",
        ).dropna()
        right_returns = pd.to_numeric(
            right_current.loc[
                right_current["is_closed"].astype(bool),
                value_column,
            ],
            errors="coerce",
        ).dropna()
        if len(left_returns) < MIN_TRADES or len(right_returns) < MIN_TRADES:
            continue
        effect = float(left_returns.mean() - right_returns.mean())
        evaluable += 1
        effects.append(effect)
        if (effect > 0 and expected_sign > 0) or (
            effect < 0 and expected_sign < 0
        ):
            stable += 1
    return {
        "bucket_count": len(buckets),
        "evaluable_leave_one_out_count": evaluable,
        "minimum_effect": finite_or_none(min(effects)) if effects else None,
        "maximum_effect": finite_or_none(max(effects)) if effects else None,
        "direction_stable_fraction": (
            finite_or_none(stable / evaluable) if evaluable else None
        ),
        "direction_stable": bool(
            evaluable > 0 and evaluable == len(buckets) and stable == evaluable
        ),
    }


def all_same_direction(values: Iterable[float | None], sign: int) -> bool:
    current = list(values)
    if not current or any(value is None for value in current):
        return False
    return all(
        (float(value) > 0 if sign > 0 else float(value) < 0)
        for value in current
    )
