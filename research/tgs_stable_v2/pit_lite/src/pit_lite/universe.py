from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import pandas as pd

from .contract import canonical_sha256


TSE_SESSION_DIVISIONS = {"1", "2"}
INCLUDED_MARKETS = {"0101", "0102", "0106", "0111", "0112"}
DOMESTIC_EQUITY_PRODUCT_VALUES = {"011"}


@dataclass(frozen=True)
class SelectionSchedule:
    year: int
    selection_date: str
    cutoff_date: str
    trailing_60_start: str
    trailing_252_start: str


@dataclass(frozen=True)
class Candidate:
    code: str
    sector: str
    liquidity: float
    completeness: float
    raw_close: float


def trading_sessions(calendar: pd.DataFrame) -> pd.DatetimeIndex:
    required = {"Date", "HolDiv"}
    if not required.issubset(calendar.columns):
        raise ValueError("calendar must include Date and HolDiv")
    dates = pd.to_datetime(
        calendar.loc[
            calendar["HolDiv"].astype(str).isin(TSE_SESSION_DIVISIONS),
            "Date",
        ]
    ).dt.tz_localize(None)
    return pd.DatetimeIndex(sorted(set(dates)))


def annual_selection_schedule(
    sessions: pd.DatetimeIndex,
    *,
    start_year: int = 2014,
    end_year: int = 2026,
) -> list[SelectionSchedule]:
    rows: list[SelectionSchedule] = []
    for year in range(start_year, end_year + 1):
        april = sessions[(sessions.year == year) & (sessions.month == 4)]
        if april.empty:
            raise ValueError(f"no April session for {year}")
        selection = pd.Timestamp(april[0])
        position = sessions.get_loc(selection)
        if not isinstance(position, int) or position < 252:
            raise ValueError(f"insufficient calendar history for {year}")
        rows.append(
            SelectionSchedule(
                year=year,
                selection_date=selection.date().isoformat(),
                cutoff_date=pd.Timestamp(sessions[position - 1]).date().isoformat(),
                trailing_60_start=pd.Timestamp(sessions[position - 60]).date().isoformat(),
                trailing_252_start=pd.Timestamp(sessions[position - 252]).date().isoformat(),
            )
        )
    return rows


def _positive_complete(frame: pd.DataFrame) -> pd.Series:
    return (
        frame[["O", "H", "L", "C", "Vo"]].notna().all(axis=1)
        & (frame[["O", "H", "L", "C"]] > 0).all(axis=1)
        & (frame["Vo"] > 0)
    )


def candidate_for_code(
    code: str,
    bars: pd.DataFrame,
    master_row: Mapping[str, Any],
    sessions: pd.DatetimeIndex,
    schedule: SelectionSchedule,
    *,
    minimum_liquidity: float,
) -> Candidate | None:
    if str(master_row.get("Mkt", "")) not in INCLUDED_MARKETS:
        return None
    product = str(master_row.get("ProdCat", "")).strip().upper()
    if product not in DOMESTIC_EQUITY_PRODUCT_VALUES:
        return None
    sector = str(master_row.get("S33", "")).strip()
    if not sector or sector in {"0", "0000", "9999"}:
        return None

    cutoff = pd.Timestamp(schedule.cutoff_date)
    selection = pd.Timestamp(schedule.selection_date)
    history = bars.loc[(bars["Code"] == code) & (bars["Date"] <= cutoff)].copy()
    if history.empty:
        return None
    first_observed = pd.Timestamp(history["Date"].min())
    if cutoff < first_observed + pd.DateOffset(years=5):
        return None

    selection_position = int(sessions.searchsorted(selection))
    expected_252 = sessions[selection_position - 252 : selection_position]
    indexed = history.set_index("Date")
    window_252 = indexed.reindex(expected_252)
    complete = _positive_complete(window_252)
    completeness = float(complete.sum() / 252.0)
    if completeness < 0.98:
        return None

    if cutoff not in indexed.index:
        return None
    cutoff_row = indexed.loc[cutoff]
    if isinstance(cutoff_row, pd.DataFrame):
        cutoff_row = cutoff_row.iloc[-1]
    raw_close = float(cutoff_row["C"])
    if not pd.notna(raw_close) or raw_close < 300:
        return None

    expected_60 = sessions[selection_position - 60 : selection_position]
    liquidity_values = pd.to_numeric(indexed.reindex(expected_60)["Va"], errors="coerce")
    liquidity = float(liquidity_values.median())
    if not pd.notna(liquidity) or liquidity < minimum_liquidity:
        return None
    return Candidate(
        code=code,
        sector=sector,
        liquidity=liquidity,
        completeness=completeness,
        raw_close=raw_close,
    )


def select_ranked_universe(
    candidates: list[Candidate],
    *,
    target_size: int,
    sector_cap: int,
) -> list[Candidate]:
    ordered = sorted(candidates, key=lambda item: (-item.liquidity, item.code))
    sector_counts: dict[str, int] = {}
    selected: list[Candidate] = []
    for candidate in ordered:
        if sector_counts.get(candidate.sector, 0) >= sector_cap:
            continue
        selected.append(candidate)
        sector_counts[candidate.sector] = sector_counts.get(candidate.sector, 0) + 1
        if len(selected) == target_size:
            break
    return selected


def composition_sha256(codes: list[str]) -> str:
    return canonical_sha256(sorted(codes))


def selection_aggregate(
    universe_id: str,
    schedule: SelectionSchedule,
    candidates: list[Candidate],
    selected: list[Candidate],
    target: int,
    *,
    evaluated_frontier_count: int | None = None,
) -> dict[str, Any]:
    sector_counts: dict[str, int] = {}
    for item in selected:
        sector_counts[item.sector] = sector_counts.get(item.sector, 0) + 1
    top_sector_share = max(sector_counts.values()) / len(selected) if selected else None
    hhi = (
        sum((count / len(selected)) ** 2 for count in sector_counts.values())
        if selected
        else None
    )
    return {
        "universe_id": universe_id,
        **asdict(schedule),
        "target_count": target,
        "eligible_count_lower_bound": len(candidates),
        "eligible_count_is_complete": False,
        "evaluated_frontier_count": (
            evaluated_frontier_count
            if evaluated_frontier_count is not None
            else len(candidates)
        ),
        "selected_count": len(selected),
        "shortfall_count": max(0, target - len(selected)),
        "sector_count": len(sector_counts),
        "top_sector_member_share": top_sector_share,
        "sector_member_hhi": hhi,
        "composition_sha256": composition_sha256([item.code for item in selected]),
    }
