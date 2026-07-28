from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from pit_lite.metrics import chronological_splits
from pit_lite.schema import normalize_bars, normalize_master, validate_security_code
from pit_lite.signals import (
    apply_membership,
    first_common_ready_session,
    signal_frame_from_bars,
)
from pit_lite.universe import annual_selection_schedule, trading_sessions

from .contract import CONTRACT, RUN_DIRECTORY, SOURCE_RUN_ID


PRIMARY_UNIVERSES = (
    "U15_ADJUSTED_STATIC",
    "U50_PIT_LITE",
    "U100_PIT_LITE",
)
COMPONENTS = tuple(CONTRACT["score_bitmask"]["bit_order"])
BIT_VALUES = {
    str(key): int(value)
    for key, value in CONTRACT["score_bitmask"]["bit_values"].items()
}


def _read_rows(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise RuntimeError(f"expected row array in {path.name}")
    return value


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected object in {path.name}")
    return value


@dataclass
class DiagnosticContext:
    run_id: str
    sessions: pd.DatetimeIndex
    splits: dict[str, dict[str, pd.Timestamp]]
    selection_dates: dict[int, str]
    membership: dict[str, Any]
    sectors: dict[tuple[int, str], str]
    bars: dict[str, pd.DataFrame]
    frames: dict[str, dict[str, pd.DataFrame]]
    signals: dict[str, pd.DataFrame]
    ledgers: dict[str, pd.DataFrame]
    curves: dict[str, pd.DataFrame]


def _sector_at(
    code: str,
    date: pd.Timestamp,
    sectors: Mapping[tuple[int, str], str],
    selection_dates: Mapping[int, str],
) -> str:
    years = [
        year
        for year, effective in sorted(selection_dates.items())
        if pd.Timestamp(effective) <= date
    ]
    year = years[-1] if years else min(selection_dates)
    return str(sectors.get((year, code), ""))


def _extended_signal_events(
    frames: Mapping[str, pd.DataFrame],
    sectors: Mapping[tuple[int, str], str],
    selection_dates: Mapping[int, str],
    static_u15: set[str],
    *,
    evaluation_start: pd.Timestamp,
    evaluation_end: pd.Timestamp,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for code, frame in sorted(frames.items()):
        selected = frame.loc[
            (frame.index >= evaluation_start)
            & (frame.index <= evaluation_end)
            & frame["indicator_ready"]
            & frame["entry_signal"]
        ]
        for date, row in selected.iterrows():
            bitmask = sum(
                BIT_VALUES[name] for name in COMPONENTS if bool(row[name])
            )
            record: dict[str, Any] = {
                "code": code,
                "signal_date": pd.Timestamp(date),
                "score": int(row["tgs_score"]),
                "bitmask": int(bitmask),
                "median_va_60": (
                    float(row["median_va_60"])
                    if pd.notna(row["median_va_60"])
                    else 0.0
                ),
                "sector": _sector_at(
                    code,
                    pd.Timestamp(date),
                    sectors,
                    selection_dates,
                ),
                "origin_group": (
                    "U15_STATIC_CODE" if code in static_u15 else "ADDED_CODE"
                ),
            }
            for name in COMPONENTS:
                record[name] = bool(row[name])
            rows.append(record)
    columns = [
        "code",
        "signal_date",
        "score",
        "bitmask",
        "median_va_60",
        "sector",
        "origin_group",
        *COMPONENTS,
    ]
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["signal_date", "code"],
        ignore_index=True,
    )


def load_context() -> DiagnosticContext:
    run = RUN_DIRECTORY
    membership = _read_object(
        run / "universe_membership" / "annual_membership.json"
    )
    if membership.get("run_id") != SOURCE_RUN_ID:
        raise RuntimeError("membership run_id mismatch")

    calendar = pd.DataFrame(_read_rows(run / "normalized" / "calendar.json"))
    calendar["Date"] = pd.to_datetime(calendar["Date"]).dt.tz_localize(None)
    all_sessions = trading_sessions(calendar)
    schedules = annual_selection_schedule(all_sessions)
    selection_dates = {item.year: item.selection_date for item in schedules}

    sectors: dict[tuple[int, str], str] = {}
    for schedule in schedules:
        master = normalize_master(
            _read_rows(
                run
                / "normalized"
                / "masters"
                / f"{schedule.year}.json"
            )
        )
        for row in master.to_dict(orient="records"):
            sectors[(schedule.year, str(row["Code"]))] = str(row["S33"])

    required_codes = {
        validate_security_code(code)
        for code in membership["U15_ADJUSTED_STATIC"]
    }
    for universe_id in ("U50_PIT_LITE", "U100_PIT_LITE"):
        for codes in membership[universe_id].values():
            required_codes.update(validate_security_code(code) for code in codes)
    bars = {
        code: normalize_bars(
            _read_rows(run / "normalized" / "bars" / f"{code}.json")
        )
        for code in sorted(required_codes)
    }

    adjusted = {
        code: signal_frame_from_bars(frame, basis="adjusted")
        for code, frame in bars.items()
    }
    static_u15 = set(membership["U15_ADJUSTED_STATIC"])
    frames: dict[str, dict[str, pd.DataFrame]] = {
        "U15_ADJUSTED_STATIC": {
            code: apply_membership(
                adjusted[code],
                code,
                static_codes=static_u15,
            )
            for code in sorted(static_u15)
        }
    }
    for universe_id in ("U50_PIT_LITE", "U100_PIT_LITE"):
        codes = sorted(
            {
                code
                for annual in membership[universe_id].values()
                for code in annual
            }
        )
        frames[universe_id] = {
            code: apply_membership(
                adjusted[code],
                code,
                annual_membership=membership[universe_id],
                selection_dates=selection_dates,
            )
            for code in codes
        }

    search_sessions = all_sessions[
        (all_sessions >= pd.Timestamp(schedules[0].selection_date))
        & (all_sessions <= pd.Timestamp("2026-07-24"))
    ]
    effective_start = first_common_ready_session(
        search_sessions,
        frames,
        {
            "U15_ADJUSTED_STATIC": membership["U15_ADJUSTED_STATIC"],
            "U50_PIT_LITE": membership["U50_PIT_LITE"],
            "U100_PIT_LITE": membership["U100_PIT_LITE"],
        },
        selection_dates,
    )
    sessions = search_sessions[search_sessions >= effective_start]
    splits = chronological_splits(sessions)
    signals = {
        universe_id: _extended_signal_events(
            universe_frames,
            sectors,
            selection_dates,
            static_u15,
            evaluation_start=effective_start,
            evaluation_end=pd.Timestamp(sessions[-1]),
        )
        for universe_id, universe_frames in frames.items()
    }
    ledgers: dict[str, pd.DataFrame] = {}
    curves: dict[str, pd.DataFrame] = {}
    for universe_id in PRIMARY_UNIVERSES:
        ledger = pd.DataFrame(
            _read_rows(
                run
                / "trade_ledger"
                / f"{universe_id}-cost_basic-ledger.json"
            )
        )
        curve = pd.DataFrame(
            _read_rows(
                run
                / "trade_ledger"
                / f"{universe_id}-cost_basic-curve.json"
            )
        )
        for column in ("signal_date", "entry_date", "exit_date"):
            ledger[column] = pd.to_datetime(ledger[column])
        curve["date"] = pd.to_datetime(curve["date"])
        ledgers[universe_id] = ledger
        curves[universe_id] = curve

    return DiagnosticContext(
        run_id=SOURCE_RUN_ID,
        sessions=pd.DatetimeIndex(sessions),
        splits=splits,
        selection_dates=selection_dates,
        membership=membership,
        sectors=sectors,
        bars=bars,
        frames=frames,
        signals=signals,
        ledgers=ledgers,
        curves=curves,
    )
