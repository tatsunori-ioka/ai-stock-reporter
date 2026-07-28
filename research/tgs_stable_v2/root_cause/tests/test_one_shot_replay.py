from __future__ import annotations

import pandas as pd
import pytest

from root_cause.data import DiagnosticContext
from root_cause.replay import one_shot_outcome


def _context(frame: pd.DataFrame, sessions: pd.DatetimeIndex) -> DiagnosticContext:
    return DiagnosticContext(
        run_id="synthetic",
        sessions=sessions,
        splits={},
        selection_dates={},
        membership={},
        sectors={},
        bars={},
        frames={"TEST": {"synthetic-code": frame}},
        signals={},
        ledgers={},
        curves={},
    )


def _candidate() -> dict[str, object]:
    return {
        "code": "synthetic-code",
        "signal_date": pd.Timestamp("2024-01-01"),
        "score": 90,
        "sector": "synthetic-sector",
    }


def _frame(sessions: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": 100.0,
            "High": 101.0,
            "Low": 99.0,
            "Close": 100.0,
            "Volume": 1_000.0,
        },
        index=sessions,
    )


def test_one_shot_uses_next_session_open_and_fixed_60_session_exit() -> None:
    sessions = pd.bdate_range("2024-01-02", periods=65)
    result = one_shot_outcome(
        _context(_frame(sessions), sessions),
        "TEST",
        _candidate(),
    )
    assert result["shadow_status"] == "COMPLETE"
    assert result["entry_date"] == sessions[0]
    assert result["exit_date"] == sessions[59]
    assert result["holding_sessions"] == 60
    assert result["exit_reason"] == "max_holding"
    assert result["horizon_10"] is not None
    assert result["horizon_20"] is not None
    assert result["horizon_40"] is not None
    assert result["horizon_60"] is not None


def test_one_shot_applies_conservative_stop_first_on_entry_session() -> None:
    sessions = pd.bdate_range("2024-01-02", periods=65)
    frame = _frame(sessions)
    frame.loc[sessions[0], ["High", "Low"]] = [140.0, 80.0]
    result = one_shot_outcome(
        _context(frame, sessions),
        "TEST",
        _candidate(),
    )
    assert result["exit_reason"] == "stop_and_take_same_day_stop_first"
    assert result["holding_sessions"] == 1
    assert result["horizon_10"] is None


def test_one_shot_recognizes_next_session_gap_exit() -> None:
    sessions = pd.bdate_range("2024-01-02", periods=65)
    frame = _frame(sessions)
    frame.loc[sessions[1], ["Open", "High", "Low", "Close"]] = [
        140.0,
        141.0,
        139.0,
        140.0,
    ]
    result = one_shot_outcome(
        _context(frame, sessions),
        "TEST",
        _candidate(),
    )
    assert result["exit_reason"] == "take_profit_gap"
    assert result["exit_date"] == sessions[1]


def test_take_profit_excursion_uses_conservative_low_before_trigger() -> None:
    sessions = pd.bdate_range("2024-01-02", periods=65)
    frame = _frame(sessions)
    frame.loc[sessions[1], ["Open", "High", "Low", "Close"]] = [
        100.0,
        135.0,
        95.0,
        130.0,
    ]
    result = one_shot_outcome(
        _context(frame, sessions),
        "TEST",
        _candidate(),
    )
    assert result["exit_reason"] == "take_profit"
    assert result["mae"] < 0
    assert result["mfe"] > 0


def test_one_shot_right_censors_when_frozen_end_arrives_first() -> None:
    sessions = pd.bdate_range("2024-01-02", periods=5)
    result = one_shot_outcome(
        _context(_frame(sessions), sessions),
        "TEST",
        _candidate(),
    )
    assert result["shadow_status"] == "RIGHT_CENSORED"
    assert result["is_closed"] is False
    assert result["net_return_pct"] is None
    assert result["exit_date"] == sessions[-1]


def test_premature_data_end_haircut_uses_frozen_evaluation_end() -> None:
    sessions = pd.bdate_range("2024-01-02", periods=65)
    frame = _frame(sessions[:5])
    result = one_shot_outcome(
        _context(frame, sessions),
        "TEST",
        _candidate(),
    )
    assert result["shadow_status"] == "COMPLETE"
    assert result["exit_reason"] == "premature_data_end_haircut"
    assert result["exit_date"] == sessions[-1]
    assert result["is_closed"] is True


def test_one_shot_rejects_missing_next_session() -> None:
    sessions = pd.bdate_range("2024-01-02", periods=5)
    candidate = _candidate()
    candidate["signal_date"] = sessions[-1]
    result = one_shot_outcome(
        _context(_frame(sessions), sessions),
        "TEST",
        candidate,
    )
    assert result == {
        "shadow_status": "MISSING_NEXT_SESSION",
        "is_closed": False,
    }
