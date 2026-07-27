from __future__ import annotations

import pandas as pd
import pytest

import pit_lite.acquisition as acquisition_module
from pit_lite.schema import normalize_master, validate_security_code
from pit_lite.signals import (
    apply_membership,
    dynamic_membership_mask,
    first_common_ready_session,
    signal_events,
)
from pit_lite.universe import (
    Candidate,
    SelectionSchedule,
    annual_selection_schedule,
    candidate_for_code,
    composition_sha256,
    select_ranked_universe,
    selection_aggregate,
)


def selection_fixture() -> tuple[pd.DatetimeIndex, SelectionSchedule]:
    sessions = pd.bdate_range("2017-01-02", "2024-04-12")
    april = sessions[(sessions.year == 2024) & (sessions.month == 4)]
    selection = pd.Timestamp(april[0])
    position = int(sessions.get_loc(selection))
    schedule = SelectionSchedule(
        year=2024,
        selection_date=selection.date().isoformat(),
        cutoff_date=pd.Timestamp(sessions[position - 1]).date().isoformat(),
        trailing_60_start=pd.Timestamp(sessions[position - 60]).date().isoformat(),
        trailing_252_start=pd.Timestamp(sessions[position - 252]).date().isoformat(),
    )
    return sessions, schedule


def qualifying_bars(
    code: str,
    sessions: pd.DatetimeIndex,
    schedule: SelectionSchedule,
    *,
    liquidity: float = 1_000_000_000.0,
    raw_close: float = 500.0,
) -> pd.DataFrame:
    selection = pd.Timestamp(schedule.selection_date)
    history_sessions = sessions[sessions < selection]
    frame = pd.DataFrame(
        {
            "Date": history_sessions,
            "Code": code,
            "O": raw_close,
            "H": raw_close * 1.01,
            "L": raw_close * 0.99,
            "C": raw_close,
            "Vo": 1_000_000.0,
            "Va": liquidity,
        }
    )
    return frame


def domestic_master(
    *,
    market: str = "0111",
    product: str = "011",
    sector: str = "0050",
) -> dict[str, str]:
    return {"Mkt": market, "ProdCat": product, "S33": sector}


def complete_master_row(**overrides: str) -> dict[str, str]:
    row = {
        "Date": "2024-03-29",
        "Code": "12340",
        "ProdCat": "011",
        "Mkt": "0111",
        "S33": "0050",
        "S33Nm": "sector",
        "CoName": "synthetic",
    }
    row.update(overrides)
    return row


def test_annual_selection_is_first_april_session_with_previous_session_cutoff() -> None:
    sessions = pd.bdate_range("2012-01-02", "2024-12-31")
    schedules = annual_selection_schedule(sessions, start_year=2014, end_year=2024)
    assert len(schedules) == 11
    for schedule in schedules:
        selection = pd.Timestamp(schedule.selection_date)
        assert selection.month == 4
        april_sessions = sessions[
            (sessions.year == schedule.year) & (sessions.month == 4)
        ]
        assert selection == april_sessions[0]
        position = int(sessions.get_loc(selection))
        assert pd.Timestamp(schedule.cutoff_date) == sessions[position - 1]
        assert pd.Timestamp(schedule.trailing_60_start) == sessions[position - 60]
        assert pd.Timestamp(schedule.trailing_252_start) == sessions[position - 252]


def test_candidate_uses_only_prior_session_information_and_domestic_product_011() -> None:
    sessions, schedule = selection_fixture()
    code = "12340"
    bars = qualifying_bars(code, sessions, schedule, liquidity=400_000_000.0)
    # A future observation must not inflate the prior-60-session liquidity rank.
    future = bars.iloc[[-1]].copy()
    future["Date"] = pd.Timestamp(schedule.selection_date)
    future["Va"] = 99_000_000_000.0
    bars = pd.concat([bars, future], ignore_index=True)
    candidate = candidate_for_code(
        code,
        bars,
        domestic_master(product="011"),
        sessions,
        schedule,
        minimum_liquidity=300_000_000.0,
    )
    assert candidate is not None
    assert candidate.liquidity == pytest.approx(400_000_000.0)
    assert candidate.completeness == 1.0


@pytest.mark.parametrize(
    ("master", "accepted"),
    [
        (domestic_master(market="0111", product="011"), True),
        (domestic_master(market="0112", product="011"), True),
        (domestic_master(market="0113", product="011"), False),
        (domestic_master(market="0105", product="011"), False),
        (domestic_master(market="0111", product="ETF"), False),
        (domestic_master(market="0111", product="011", sector=""), False),
    ],
)
def test_candidate_market_product_and_sector_filters(
    master: dict[str, str],
    accepted: bool,
) -> None:
    sessions, schedule = selection_fixture()
    bars = qualifying_bars("12340", sessions, schedule)
    actual = candidate_for_code(
        "12340",
        bars,
        master,
        sessions,
        schedule,
        minimum_liquidity=300_000_000.0,
    )
    assert (actual is not None) is accepted


def test_master_without_product_category_fails_closed() -> None:
    row = complete_master_row()
    del row["ProdCat"]
    normalized = normalize_master([row])
    assert normalized["ProdCat"].tolist() == [""]
    assert acquisition_module._valid_master(normalized).empty


@pytest.mark.parametrize(
    ("product", "accepted"),
    [
        ("011", True),
        (" 011 ", True),
        ("", False),
        ("01", False),
        ("1", False),
        ("02", False),
        ("STOCK", False),
        ("DOMESTIC_EQUITY", False),
    ],
)
def test_only_frozen_product_category_011_is_accepted(
    product: str,
    accepted: bool,
) -> None:
    master = normalize_master([complete_master_row(ProdCat=product)])
    assert (not acquisition_module._valid_master(master).empty) is accepted


@pytest.mark.parametrize(
    "unsafe",
    [
        "../../raw",
        "12340/../../secret",
        "/12340",
        "1234",
        "１２３４０",
        "١٢٣٤٠",
        "12340.json",
    ],
)
def test_security_code_rejects_path_traversal_and_non_ascii_digits(
    unsafe: str,
) -> None:
    with pytest.raises(ValueError, match="uppercase ASCII"):
        validate_security_code(unsafe)


def test_uppercase_alphanumeric_security_code_is_valid_and_path_safe() -> None:
    assert validate_security_code("1234A") == "1234A"


def test_code_history_loader_validates_code_before_building_path(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        acquisition_module,
        "_read_frame",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unsafe path reached frame reader")
        ),
    )
    with pytest.raises(ValueError, match="uppercase ASCII"):
        acquisition_module._load_code_bars(tmp_path, "../../outside")


def test_candidate_requires_five_calendar_years_from_first_observed_bar() -> None:
    sessions, schedule = selection_fixture()
    code = "12340"
    bars = qualifying_bars(code, sessions, schedule)
    too_recent = bars.loc[
        bars["Date"] > pd.Timestamp(schedule.selection_date) - pd.DateOffset(years=5)
    ]
    assert (
        candidate_for_code(
            code,
            too_recent,
            domestic_master(),
            sessions,
            schedule,
            minimum_liquidity=300_000_000.0,
        )
        is None
    )
    assert (
        candidate_for_code(
            code,
            bars,
            domestic_master(),
            sessions,
            schedule,
            minimum_liquidity=300_000_000.0,
        )
        is not None
    )


def test_candidate_completeness_boundary_is_98_percent_of_252_sessions() -> None:
    sessions, schedule = selection_fixture()
    code = "12340"
    base = qualifying_bars(code, sessions, schedule)
    selection_position = int(sessions.get_loc(pd.Timestamp(schedule.selection_date)))
    expected = sessions[selection_position - 252 : selection_position]

    pass_frame = base.loc[~base["Date"].isin(expected[:5])].copy()
    accepted = candidate_for_code(
        code,
        pass_frame,
        domestic_master(),
        sessions,
        schedule,
        minimum_liquidity=300_000_000.0,
    )
    assert accepted is not None
    assert accepted.completeness == pytest.approx(247 / 252)

    fail_frame = base.loc[~base["Date"].isin(expected[:6])].copy()
    assert (
        candidate_for_code(
            code,
            fail_frame,
            domestic_master(),
            sessions,
            schedule,
            minimum_liquidity=300_000_000.0,
        )
        is None
    )


@pytest.mark.parametrize(
    ("mutator", "minimum_liquidity"),
    [
        ("nonpositive_ohlcv", 300_000_000.0),
        ("raw_close_below_300", 300_000_000.0),
        ("liquidity_below_threshold", 1_000_000_000.0),
    ],
)
def test_candidate_tradeability_close_and_liquidity_gates(
    mutator: str,
    minimum_liquidity: float,
) -> None:
    sessions, schedule = selection_fixture()
    code = "12340"
    bars = qualifying_bars(code, sessions, schedule, liquidity=400_000_000.0)
    cutoff = pd.Timestamp(schedule.cutoff_date)
    if mutator == "nonpositive_ohlcv":
        selection_position = int(sessions.get_loc(pd.Timestamp(schedule.selection_date)))
        expected = sessions[selection_position - 252 : selection_position]
        bars.loc[bars["Date"].isin(expected[:6]), "Vo"] = 0
    elif mutator == "raw_close_below_300":
        bars.loc[bars["Date"] == cutoff, "C"] = 299.99
    result = candidate_for_code(
        code,
        bars,
        domestic_master(),
        sessions,
        schedule,
        minimum_liquidity=minimum_liquidity,
    )
    assert result is None


def candidate(
    code: str,
    sector: str,
    liquidity: float,
) -> Candidate:
    return Candidate(
        code=code,
        sector=sector,
        liquidity=liquidity,
        completeness=1.0,
        raw_close=500.0,
    )


def test_rank_is_liquidity_desc_then_code_asc_and_sector_cap_never_relaxes() -> None:
    candidates = [
        candidate("30000", "A", 900.0),
        candidate("10000", "A", 1_000.0),
        candidate("20000", "A", 1_000.0),
        candidate("40000", "B", 800.0),
    ]
    selected = select_ranked_universe(candidates, target_size=4, sector_cap=2)
    assert [item.code for item in selected] == ["10000", "20000", "40000"]
    assert len(selected) == 3


def test_selection_aggregate_contains_hash_and_counts_not_composition() -> None:
    _, schedule = selection_fixture()
    candidates = [
        candidate("10000", "A", 1000.0),
        candidate("20000", "B", 900.0),
    ]
    aggregate = selection_aggregate("U50_PIT_LITE", schedule, candidates, candidates, 50)
    assert aggregate["selected_count"] == 2
    assert aggregate["shortfall_count"] == 48
    assert aggregate["composition_sha256"] == composition_sha256(["10000", "20000"])
    serialized = str(aggregate)
    assert "10000" not in serialized
    assert "20000" not in serialized


def test_membership_is_fixed_between_april_rebalances_and_changes_on_effective_date() -> None:
    dates = pd.to_datetime(
        ["2024-03-29", "2024-04-01", "2025-03-31", "2025-04-01", "2025-04-02"]
    )
    selection_dates = {2024: "2024-04-01", 2025: "2025-04-01"}
    membership = {"2024": ["11110"], "2025": []}
    mask = dynamic_membership_mask(dates, "11110", membership, selection_dates)
    assert mask.tolist() == [False, True, True, False, False]


def test_signal_is_suppressed_outside_membership_without_changing_score() -> None:
    dates = pd.to_datetime(["2024-03-29", "2024-04-01", "2025-04-01"])
    frame = pd.DataFrame(
        {
            "indicator_ready": True,
            "entry_signal": True,
            "tgs_score": [120, 120, 120],
            "median_va_60": 1_000_000_000.0,
        },
        index=dates,
    )
    result = apply_membership(
        frame,
        "11110",
        annual_membership={"2024": ["11110"], "2025": []},
        selection_dates={2024: "2024-04-01", 2025: "2025-04-01"},
    )
    assert result["entry_signal"].tolist() == [False, True, False]
    assert result["tgs_score"].tolist() == [120, 120, 120]


def test_signal_events_only_emit_ready_in_period_member_events() -> None:
    dates = pd.bdate_range("2024-04-01", periods=4)
    frame = pd.DataFrame(
        {
            "indicator_ready": [False, True, True, True],
            "entry_signal": [True, True, False, True],
            "tgs_score": [100, 90, 0, 120],
            "median_va_60": [1.0, 2.0, 3.0, 4.0],
        },
        index=dates,
    )
    events = signal_events(
        {"11110": frame},
        {(2024, "11110"): "0050"},
        {2024: "2024-04-01"},
        evaluation_start=dates[1],
        evaluation_end=dates[2],
    )
    assert len(events) == 1
    assert events.iloc[0]["signal_date"] == dates[1]
    assert events.iloc[0]["score"] == 90
    assert events.iloc[0]["sector"] == "0050"


def test_first_common_ready_session_requires_every_active_member() -> None:
    sessions = pd.bdate_range("2024-04-01", periods=4)
    first = pd.DataFrame(
        {"indicator_ready": [False, True, True, True]},
        index=sessions,
    )
    second = pd.DataFrame(
        {"indicator_ready": [False, False, True, True]},
        index=sessions,
    )
    actual = first_common_ready_session(
        sessions,
        {"U50": {"11110": first, "22220": second}},
        {"U50": {"2024": ["11110", "22220"]}},
        {2024: "2024-04-01"},
    )
    assert actual == sessions[2]
