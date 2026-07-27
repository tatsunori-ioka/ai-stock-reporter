from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from tgs_stable_v2.indicators import build_signal_frame

from .schema import price_frame


def signal_frame_from_bars(bars: pd.DataFrame, *, basis: str) -> pd.DataFrame:
    prices = price_frame(bars, basis)
    result = build_signal_frame(prices)
    traded_value = (
        bars.set_index("Date")["Va"]
        .loc[lambda value: ~value.index.duplicated(keep="last")]
        .sort_index()
    )
    result["Va"] = pd.to_numeric(traded_value.reindex(result.index), errors="coerce")
    result["median_va_60"] = result["Va"].rolling(60, min_periods=60).median()
    return result


def dynamic_membership_mask(
    dates: pd.DatetimeIndex,
    code: str,
    annual_membership: Mapping[str, list[str]],
    selection_dates: Mapping[int, str],
) -> pd.Series:
    mask = pd.Series(False, index=dates, dtype=bool)
    ordered = sorted((year, pd.Timestamp(value)) for year, value in selection_dates.items())
    for position, (year, start) in enumerate(ordered):
        end = (
            ordered[position + 1][1] - pd.Timedelta(nanoseconds=1)
            if position + 1 < len(ordered)
            else pd.Timestamp.max
        )
        if code in set(annual_membership.get(str(year), [])):
            mask.loc[(mask.index >= start) & (mask.index <= end)] = True
    return mask


def apply_membership(
    frame: pd.DataFrame,
    code: str,
    *,
    static_codes: set[str] | None = None,
    annual_membership: Mapping[str, list[str]] | None = None,
    selection_dates: Mapping[int, str] | None = None,
) -> pd.DataFrame:
    result = frame.copy()
    if static_codes is not None:
        mask = pd.Series(code in static_codes, index=result.index, dtype=bool)
    else:
        if annual_membership is None or selection_dates is None:
            raise ValueError("dynamic membership inputs are required")
        mask = dynamic_membership_mask(
            pd.DatetimeIndex(result.index),
            code,
            annual_membership,
            selection_dates,
        )
    result["universe_member"] = mask
    result["entry_signal"] = result["entry_signal"] & result["universe_member"]
    return result


def signal_events(
    frames: Mapping[str, pd.DataFrame],
    sectors: Mapping[tuple[int, str], str],
    selection_dates: Mapping[int, str],
    *,
    evaluation_start: pd.Timestamp,
    evaluation_end: pd.Timestamp,
) -> pd.DataFrame:
    selection_order = sorted(
        (pd.Timestamp(date), year) for year, date in selection_dates.items()
    )

    def sector_at(code: str, date: pd.Timestamp) -> str:
        eligible = [year for effective, year in selection_order if effective <= date]
        year = eligible[-1] if eligible else selection_order[0][1]
        return sectors.get((year, code), "")

    rows: list[dict[str, Any]] = []
    for code, frame in sorted(frames.items()):
        selected = frame.loc[
            (frame.index >= evaluation_start)
            & (frame.index <= evaluation_end)
            & frame["indicator_ready"]
            & frame["entry_signal"]
        ]
        for date, row in selected.iterrows():
            rows.append(
                {
                    "code": code,
                    "signal_date": pd.Timestamp(date),
                    "score": int(row["tgs_score"]),
                    "median_va_60": float(row["median_va_60"])
                    if pd.notna(row["median_va_60"])
                    else 0.0,
                    "sector": sector_at(code, pd.Timestamp(date)),
                }
            )
    columns = ["code", "signal_date", "score", "median_va_60", "sector"]
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["signal_date", "code"],
        ignore_index=True,
    )


def first_common_ready_session(
    sessions: pd.DatetimeIndex,
    universe_frames: Mapping[str, Mapping[str, pd.DataFrame]],
    membership_by_universe: Mapping[str, Mapping[str, list[str]] | list[str]],
    selection_dates: Mapping[int, str],
) -> pd.Timestamp:
    dynamic_years = sorted(selection_dates)
    for session in sessions:
        all_ready = True
        for universe_id, frames in universe_frames.items():
            membership = membership_by_universe[universe_id]
            if isinstance(membership, list):
                active = membership
            else:
                eligible_years = [
                    year
                    for year in dynamic_years
                    if pd.Timestamp(selection_dates[year]) <= session
                ]
                if not eligible_years:
                    all_ready = False
                    break
                active = membership.get(str(eligible_years[-1]), [])
            if not active:
                all_ready = False
                break
            for code in active:
                frame = frames.get(code)
                if frame is None:
                    all_ready = False
                    break
                known = frame.loc[frame.index <= session]
                if known.empty or not bool(known.iloc[-1]["indicator_ready"]):
                    all_ready = False
                    break
            if not all_ready:
                break
        if all_ready:
            return pd.Timestamp(session)
    raise RuntimeError("no common indicator-ready JPX session")
