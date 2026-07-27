from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from pit_lite.execution import rank_candidates, simulate_capital_proxy
from tgs_stable_v2.config import (
    COST_SCENARIOS,
    MAX_HOLDING_DAYS,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
)

from .contract import CONTRACT, PIT_ROOT, canonical_sha256
from .data import DiagnosticContext


GAP_REASONS = {"stop_gap", "take_profit_gap"}


def _valid_bar(row: pd.Series) -> bool:
    values = [row.get(key) for key in ("Open", "High", "Low", "Close", "Volume")]
    return all(pd.notna(value) and float(value) > 0 for value in values)


def _as_dates(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        result[column] = pd.to_datetime(result[column]).dt.strftime("%Y-%m-%d")
    return result


def _assert_frames_equal(
    actual: pd.DataFrame,
    expected: pd.DataFrame,
    *,
    label: str,
    date_columns: tuple[str, ...],
    string_columns: tuple[str, ...],
    numeric_columns: tuple[str, ...],
) -> None:
    if len(actual) != len(expected):
        raise RuntimeError(f"{label} row-count mismatch")
    left = _as_dates(actual, date_columns).reset_index(drop=True)
    right = _as_dates(expected, date_columns).reset_index(drop=True)
    for column in (*date_columns, *string_columns):
        if left[column].fillna("").astype(str).tolist() != right[column].fillna(
            ""
        ).astype(str).tolist():
            raise RuntimeError(f"{label} {column} mismatch")
    for column in numeric_columns:
        left_values = pd.to_numeric(left[column], errors="coerce").to_numpy()
        right_values = pd.to_numeric(right[column], errors="coerce").to_numpy()
        if not np.allclose(
            left_values,
            right_values,
            rtol=1e-11,
            atol=1e-8,
            equal_nan=True,
        ):
            raise RuntimeError(f"{label} {column} mismatch")


def verify_frozen_primary_replay(
    context: DiagnosticContext,
) -> dict[str, Any]:
    source_summary = json.loads(
        (PIT_ROOT / "results" / "metrics_summary.json").read_text(encoding="utf-8")
    )
    results: dict[str, Any] = {}
    for universe_id in context.ledgers:
        actual_ledger, actual_curve, counters = simulate_capital_proxy(
            context.signals[universe_id],
            context.frames[universe_id],
            context.sessions,
            cost=COST_SCENARIOS["basic"],
            path_policy="conservative",
            terminal_policy="haircut_20",
        )
        expected_ledger = context.ledgers[universe_id].sort_values(
            ["signal_date", "code", "entry_date"],
            ignore_index=True,
        )
        expected_curve = context.curves[universe_id].reset_index(drop=True)
        _assert_frames_equal(
            actual_ledger,
            expected_ledger,
            label=f"{universe_id} primary ledger",
            date_columns=(
                "signal_date",
                "entry_date",
                "exit_date",
                "last_observed_bar_date",
            ),
            string_columns=(
                "code",
                "ticker",
                "sector",
                "exit_reason",
                "data_quality_status",
            ),
            numeric_columns=(
                "score",
                "signal_median_va",
                "shares",
                "entry_raw_open",
                "entry_fill_price",
                "exit_raw_price",
                "exit_fill_price",
                "holding_sessions",
                "net_return_pct",
                "is_closed",
            ),
        )
        _assert_frames_equal(
            actual_curve,
            expected_curve,
            label=f"{universe_id} primary curve",
            date_columns=("date",),
            string_columns=(),
            numeric_columns=(
                "equity",
                "cash",
                "active_positions",
                "cash_utilization",
            ),
        )
        expected_counters = {
            key: int(source_summary["universes"][universe_id]["primary"][key])
            for key in counters
        }
        if counters != expected_counters:
            raise RuntimeError(f"{universe_id} primary counter mismatch")
        results[universe_id] = {
            "ledger_rows": len(actual_ledger),
            "curve_rows": len(actual_curve),
            "counters": counters,
            "aggregate_replay_sha256": canonical_sha256(
                {
                    "ledger_rows": len(actual_ledger),
                    "curve_rows": len(actual_curve),
                    "closed_rows": int(actual_ledger["is_closed"].astype(bool).sum()),
                    "sum_net_returns": float(
                        pd.to_numeric(
                            actual_ledger["net_return_pct"],
                            errors="coerce",
                        ).sum()
                    ),
                    "final_equity": float(actual_curve.iloc[-1]["equity"]),
                    "counters": counters,
                }
            ),
            "match": True,
        }
    return results


def _position_active_after_close(
    ledger: pd.DataFrame,
    code: str,
    signal_date: pd.Timestamp,
) -> bool:
    rows = ledger.loc[
        (ledger["code"].astype(str) == code)
        & (pd.to_datetime(ledger["entry_date"]) <= signal_date)
        & (pd.to_datetime(ledger["exit_date"]) > signal_date)
    ]
    return not rows.empty


def _occupied_at_open(
    ledger: pd.DataFrame,
    entry_date: pd.Timestamp,
) -> set[str]:
    prior = ledger.loc[pd.to_datetime(ledger["entry_date"]) < entry_date].copy()
    exit_dates = pd.to_datetime(prior["exit_date"])
    still_open = exit_dates > entry_date
    same_day_non_gap = (exit_dates == entry_date) & ~prior["exit_reason"].isin(
        GAP_REASONS
    )
    return set(prior.loc[still_open | same_day_non_gap, "code"].astype(str))


def classify_signal_dispositions(
    context: DiagnosticContext,
    universe_id: str,
) -> pd.DataFrame:
    signals = context.signals[universe_id].copy()
    ledger = context.ledgers[universe_id].copy()
    accepted_keys = {
        (
            str(row.code),
            pd.Timestamp(row.signal_date),
            pd.Timestamp(row.entry_date),
        )
        for row in ledger.itertuples(index=False)
    }
    session_count = len(context.sessions)
    scheduled: dict[pd.Timestamp, list[dict[str, Any]]] = {}
    decisions: list[dict[str, Any]] = []
    for row in signals.to_dict(orient="records"):
        signal_date = pd.Timestamp(row["signal_date"])
        next_position = int(context.sessions.searchsorted(signal_date, side="right"))
        base = dict(row)
        if next_position >= session_count:
            decisions.append(
                {
                    **base,
                    "entry_date": pd.NaT,
                    "disposition": "missing_next_session",
                }
            )
            continue
        entry_date = pd.Timestamp(context.sessions[next_position])
        if _position_active_after_close(
            ledger,
            str(row["code"]),
            signal_date,
        ):
            decisions.append(
                {
                    **base,
                    "entry_date": entry_date,
                    "disposition": "duplicate_rejected",
                }
            )
            continue
        scheduled.setdefault(entry_date, []).append(base)

    maximum_positions = int(CONTRACT["rules"]["maximum_positions"])
    for entry_date, rows in sorted(scheduled.items()):
        occupied = _occupied_at_open(ledger, entry_date)
        ranked = rank_candidates(pd.DataFrame(rows))
        current: list[dict[str, Any]] = []
        for row in ranked.to_dict(orient="records"):
            code = str(row["code"])
            key = (code, pd.Timestamp(row["signal_date"]), entry_date)
            if code in occupied:
                disposition = "duplicate_rejected"
            elif key in accepted_keys:
                if len(occupied) >= maximum_positions:
                    raise RuntimeError("accepted candidate exceeds frozen capacity")
                disposition = "accepted"
                occupied.add(code)
            elif len(occupied) >= maximum_positions:
                disposition = "capacity_rejected"
            else:
                frame = context.frames[universe_id].get(code)
                if frame is None or entry_date not in frame.index:
                    disposition = "missing_next_session"
                else:
                    bar = frame.loc[entry_date]
                    if isinstance(bar, pd.DataFrame):
                        bar = bar.iloc[-1]
                    disposition = (
                        "invalid_bar"
                        if not _valid_bar(bar)
                        else "capacity_rejected"
                    )
            current.append(
                {
                    **row,
                    "entry_date": entry_date,
                    "disposition": disposition,
                }
            )
        binding = any(
            row["disposition"] == "capacity_rejected" for row in current
        )
        for row in current:
            decisions.append({**row, "capacity_binding_session": binding})

    result = pd.DataFrame(decisions)
    if "capacity_binding_session" not in result:
        result["capacity_binding_session"] = False
    result["capacity_binding_session"] = result[
        "capacity_binding_session"
    ].fillna(False)
    result = result.sort_values(
        ["signal_date", "code"],
        ignore_index=True,
    )
    source_summary = json.loads(
        (PIT_ROOT / "results" / "metrics_summary.json").read_text(encoding="utf-8")
    )
    expected = source_summary["universes"][universe_id]["primary"]
    observed = result["disposition"].value_counts().to_dict()
    checks = {
        "raw_signals": len(result),
        "accepted_entries": int(observed.get("accepted", 0)),
        "capacity_rejections": int(observed.get("capacity_rejected", 0)),
        "duplicate_rejections": int(observed.get("duplicate_rejected", 0)),
        "missing_next_session_rejections": int(
            observed.get("missing_next_session", 0)
        ),
        "invalid_bar_rejections": int(observed.get("invalid_bar", 0)),
    }
    for key, value in checks.items():
        if value != int(expected[key]):
            raise RuntimeError(
                f"{universe_id} disposition replay mismatch for {key}: "
                f"{value} != {expected[key]}"
            )
    return result


def one_shot_outcome(
    context: DiagnosticContext,
    universe_id: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    code = str(candidate["code"])
    signal_date = pd.Timestamp(candidate["signal_date"])
    entry_position = int(context.sessions.searchsorted(signal_date, side="right"))
    if entry_position >= len(context.sessions):
        return {"shadow_status": "MISSING_NEXT_SESSION", "is_closed": False}
    entry_date = pd.Timestamp(context.sessions[entry_position])
    frame = context.frames[universe_id].get(code)
    if frame is None or entry_date not in frame.index:
        return {"shadow_status": "MISSING_NEXT_SESSION", "is_closed": False}
    entry_bar = frame.loc[entry_date]
    if isinstance(entry_bar, pd.DataFrame):
        entry_bar = entry_bar.iloc[-1]
    if not _valid_bar(entry_bar):
        return {"shadow_status": "INVALID_BAR", "is_closed": False}

    cost = COST_SCENARIOS["basic"]
    commission = cost.commission_rate
    slippage = cost.slippage_rate
    entry_raw = float(entry_bar["Open"])
    entry_fill = entry_raw * (1.0 + slippage)
    entry_cash = entry_fill * (1.0 + commission)
    stop_price = entry_fill * (1.0 + STOP_LOSS_PCT)
    take_price = entry_fill * (1.0 + TAKE_PROFIT_PCT)
    holding = 0
    last_close = float(entry_bar["Close"])
    last_bar_date = entry_date
    mfe = 0.0
    mae = 0.0
    horizons: dict[int, float | None] = {10: None, 20: None, 40: None, 60: None}
    exit_reason: str | None = None
    exit_raw: float | None = None

    for session in context.sessions[entry_position:]:
        session = pd.Timestamp(session)
        if session not in frame.index:
            continue
        bar = frame.loc[session]
        if isinstance(bar, pd.DataFrame):
            bar = bar.iloc[-1]
        if not _valid_bar(bar):
            continue
        holding += 1
        raw_open = float(bar["Open"])
        high = float(bar["High"])
        low = float(bar["Low"])
        close = float(bar["Close"])
        last_close = close
        last_bar_date = session
        is_entry = session == entry_date

        if not is_entry and raw_open <= stop_price:
            exit_reason, exit_raw = "stop_gap", raw_open
        elif not is_entry and raw_open >= take_price:
            exit_reason, exit_raw = "take_profit_gap", raw_open
        else:
            stop_hit = low <= stop_price
            take_hit = high >= take_price
            if stop_hit and take_hit:
                exit_reason, exit_raw = (
                    "stop_and_take_same_day_stop_first",
                    stop_price,
                )
            elif stop_hit:
                exit_reason, exit_raw = "stop_loss", stop_price
            elif take_hit:
                exit_reason, exit_raw = "take_profit", take_price
            elif holding >= MAX_HOLDING_DAYS:
                exit_reason, exit_raw = "max_holding", close

        if exit_reason in GAP_REASONS:
            path_high = path_low = raw_open
        elif exit_reason in {
            "stop_loss",
            "stop_and_take_same_day_stop_first",
        }:
            path_high = max(raw_open, float(exit_raw))
            path_low = float(exit_raw)
        elif exit_reason == "take_profit":
            # Under the frozen conservative path, a non-stop low may occur
            # before the take trigger. Prices after the trigger are excluded.
            path_high = max(raw_open, float(exit_raw))
            path_low = low
        else:
            path_high, path_low = high, low
        mfe = max(mfe, path_high / entry_cash - 1.0)
        mae = min(mae, path_low / entry_cash - 1.0)

        if holding in horizons and (
            exit_reason is None or exit_reason == "max_holding"
        ):
            horizons[holding] = close / entry_cash - 1.0
        if exit_reason is not None:
            break

    if exit_reason is None:
        if last_bar_date < pd.Timestamp(context.sessions[-1]):
            exit_reason = "premature_data_end_haircut"
            exit_raw = last_close * 0.8
        else:
            return {
                "shadow_status": "RIGHT_CENSORED",
                "signal_date": signal_date,
                "entry_date": entry_date,
                "exit_date": pd.Timestamp(context.sessions[-1]),
                "score": int(candidate["score"]),
                "sector": str(candidate.get("sector", "")),
                "code": code,
                "holding_sessions": holding,
                "mfe": mfe,
                "mae": mae,
                **{f"horizon_{key}": value for key, value in horizons.items()},
                "is_closed": False,
                "net_return_pct": None,
                "exit_reason": "open_at_frozen_end",
            }
    assert exit_raw is not None
    exit_fill = float(exit_raw) * (1.0 - slippage)
    net_return = exit_fill * (1.0 - commission) / entry_cash - 1.0
    return {
        "shadow_status": "COMPLETE",
        "signal_date": signal_date,
        "entry_date": entry_date,
        "exit_date": (
            pd.Timestamp(context.sessions[-1])
            if exit_reason == "premature_data_end_haircut"
            else last_bar_date
        ),
        "score": int(candidate["score"]),
        "sector": str(candidate.get("sector", "")),
        "code": code,
        "holding_sessions": holding,
        "mfe": float(mfe),
        "mae": float(mae),
        **{f"horizon_{key}": value for key, value in horizons.items()},
        "is_closed": True,
        "net_return_pct": float(net_return),
        "exit_reason": exit_reason,
    }


def build_shadow_outcomes(
    context: DiagnosticContext,
    universe_id: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for candidate in context.signals[universe_id].to_dict(orient="records"):
        outcome = one_shot_outcome(context, universe_id, candidate)
        rows.append(
            {
                **candidate,
                **outcome,
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["signal_date", "code"],
        ignore_index=True,
    )
