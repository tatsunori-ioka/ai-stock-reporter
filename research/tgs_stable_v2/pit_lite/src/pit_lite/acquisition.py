from __future__ import annotations

import math
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .api import (
    HttpStatusError,
    ResponseTooLarge,
    SafeApiClient,
    frozen_acquisition_plan,
)
from .contract import (
    CONTRACT,
    CONTRACT_PATH,
    PIT_ROOT,
    canonical_sha256,
    read_json,
    sha256_file,
)
from .manifest import build_deletion_manifest
from .safety import atomic_write_bytes, atomic_write_json, read_json as read_private_json
from .schema import normalize_bars, normalize_master, validate_security_code
from .universe import (
    DOMESTIC_EQUITY_PRODUCT_VALUES,
    INCLUDED_MARKETS,
    Candidate,
    SelectionSchedule,
    annual_selection_schedule,
    candidate_for_code,
    select_ranked_universe,
    selection_aggregate,
    trading_sessions,
)


U50_THRESHOLD = 1_000_000_000.0
U100_THRESHOLD = 300_000_000.0
U50_TARGET = 50
U100_TARGET = 100
U50_SECTOR_CAP = 8
U100_SECTOR_CAP = 15


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def acquisition_implementation_sha256() -> str:
    paths = [
        PIT_ROOT / "scripts" / "acquire_jquants_pit_lite.py",
        *[
            PIT_ROOT / "src" / "pit_lite" / name
            for name in (
                "acquisition.py",
                "api.py",
                "contract.py",
                "manifest.py",
                "safety.py",
                "schema.py",
                "universe.py",
            )
        ],
    ]
    return canonical_sha256(
        [
            (str(path.relative_to(PIT_ROOT)), sha256_file(path))
            for path in sorted(paths)
        ]
    )


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    copy = frame.copy()
    for column in copy.columns:
        if pd.api.types.is_datetime64_any_dtype(copy[column]):
            copy[column] = copy[column].dt.strftime("%Y-%m-%d")
    copy = copy.astype(object).where(pd.notna(copy), None)
    return copy.to_dict(orient="records")


def _write_frame(path: Path, frame: pd.DataFrame) -> None:
    atomic_write_json(path, _records(frame))


def _read_frame(path: Path, *, kind: str) -> pd.DataFrame:
    rows = read_private_json(path)
    if kind == "bars":
        return normalize_bars(rows)
    if kind == "master":
        return normalize_master(rows)
    frame = pd.DataFrame(rows)
    frame["Date"] = pd.to_datetime(frame["Date"]).dt.tz_localize(None)
    return frame


def load_u15_codes() -> list[str]:
    config_path = Path(__file__).resolve().parents[3] / "config" / "universe_u15.yaml"
    config = read_json(config_path)
    return [
        str(item["ticker"]).split(".", 1)[0].zfill(4) + "0"
        for item in config["tickers"]
    ]


def _valid_master(master: pd.DataFrame) -> pd.DataFrame:
    product = master["ProdCat"].astype(str).str.strip().str.upper()
    sector = master["S33"].astype(str).str.strip()
    return master.loc[
        master["Mkt"].isin(INCLUDED_MARKETS)
        & product.isin(DOMESTIC_EQUITY_PRODUCT_VALUES)
        & sector.ne("")
        & ~sector.isin({"0", "0000", "9999"})
    ].copy()


def _preliminary_rank(
    master: pd.DataFrame,
    discovery: pd.DataFrame,
    sessions: pd.DatetimeIndex,
    schedule: SelectionSchedule,
) -> list[dict[str, Any]]:
    valid_master = _valid_master(master).drop_duplicates("Code", keep="last")
    selection = pd.Timestamp(schedule.selection_date)
    position = int(sessions.searchsorted(selection))
    expected = sessions[position - 60 : position]
    cutoff = pd.Timestamp(schedule.cutoff_date)
    bars = discovery.loc[discovery["Date"].isin(expected)].copy()
    indexed = bars.set_index(["Code", "Date"]).sort_index()
    rows: list[dict[str, Any]] = []
    for master_row in valid_master.to_dict(orient="records"):
        code = str(master_row["Code"])
        try:
            code_bars = indexed.loc[code]
        except KeyError:
            continue
        values = pd.to_numeric(code_bars.reindex(expected)["Va"], errors="coerce")
        liquidity = float(values.median())
        if not math.isfinite(liquidity) or liquidity < U100_THRESHOLD:
            continue
        if cutoff not in code_bars.index:
            continue
        cutoff_row = code_bars.loc[cutoff]
        if isinstance(cutoff_row, pd.DataFrame):
            cutoff_row = cutoff_row.iloc[-1]
        raw_close = float(cutoff_row["C"])
        if not math.isfinite(raw_close) or raw_close < 300:
            continue
        rows.append(
            {
                "code": code,
                "liquidity": liquidity,
                "sector": str(master_row["S33"]),
            }
        )
    return sorted(rows, key=lambda item: (-item["liquidity"], item["code"]))


def _chunked(values: list[pd.Timestamp], size: int) -> list[list[pd.Timestamp]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _load_code_bars(run_directory: Path, code: str) -> pd.DataFrame:
    code = validate_security_code(code)
    return _read_frame(run_directory / "normalized" / "bars" / f"{code}.json", kind="bars")


def _evaluate_year(
    year: int,
    schedule: SelectionSchedule,
    master: pd.DataFrame,
    processed: list[dict[str, Any]],
    available_bars: dict[str, pd.DataFrame],
    sessions: pd.DatetimeIndex,
) -> dict[str, Any]:
    master_by_code = {
        str(row["Code"]): row for row in master.to_dict(orient="records")
    }
    candidates_100: list[Candidate] = []
    candidates_50: list[Candidate] = []
    for item in processed:
        code = str(item["code"])
        bars = available_bars.get(code)
        master_row = master_by_code.get(code)
        if bars is None or master_row is None:
            continue
        candidate_100 = candidate_for_code(
            code,
            bars,
            master_row,
            sessions,
            schedule,
            minimum_liquidity=U100_THRESHOLD,
        )
        if candidate_100 is not None:
            candidates_100.append(candidate_100)
        candidate_50 = candidate_for_code(
            code,
            bars,
            master_row,
            sessions,
            schedule,
            minimum_liquidity=U50_THRESHOLD,
        )
        if candidate_50 is not None:
            candidates_50.append(candidate_50)
    selected_100 = select_ranked_universe(
        candidates_100,
        target_size=U100_TARGET,
        sector_cap=U100_SECTOR_CAP,
    )
    selected_50 = select_ranked_universe(
        candidates_50,
        target_size=U50_TARGET,
        sector_cap=U50_SECTOR_CAP,
    )
    return {
        "year": year,
        "u100_candidates": candidates_100,
        "u100_selected": selected_100,
        "u50_candidates": candidates_50,
        "u50_selected": selected_50,
    }


def _year_done(
    preliminary: list[dict[str, Any]],
    pointer: int,
    evaluation: dict[str, Any],
) -> bool:
    exhausted = pointer >= len(preliminary)
    u100_done = len(evaluation["u100_selected"]) >= U100_TARGET or exhausted
    next_below_u50 = exhausted or preliminary[pointer]["liquidity"] < U50_THRESHOLD
    u50_done = len(evaluation["u50_selected"]) >= U50_TARGET or next_below_u50
    return u100_done and u50_done


def acquire(
    client: SafeApiClient,
    run_id: str,
    run_directory: Path,
    *,
    external_prior_attempts: int = 0,
) -> dict[str, Any]:
    plan = frozen_acquisition_plan()
    fallback_worst = int(
        CONTRACT["api"]["rank_window_fallback"]["planned_worst_case_attempts"]
    )
    if (
        not isinstance(external_prior_attempts, int)
        or external_prior_attempts < 0
        or external_prior_attempts
        + max(plan.planned_worst_case_attempts, fallback_worst)
        > plan.hard_attempt_limit
    ):
        raise RuntimeError("external prior attempts exceed the frozen gate budget")
    checkpoint_path = run_directory / "checkpoint" / "acquisition.json"
    contract_sha256 = sha256_file(CONTRACT_PATH)
    implementation_sha256 = acquisition_implementation_sha256()
    if checkpoint_path.is_file():
        checkpoint = read_private_json(checkpoint_path)
        expected_resume_values = {
            "run_id": run_id,
            "plan_sha256": plan.sha256,
            "contract_sha256": contract_sha256,
            "acquisition_implementation_sha256": implementation_sha256,
            "external_prior_attempts": external_prior_attempts,
        }
        mismatches = [
            name
            for name, expected in expected_resume_values.items()
            if checkpoint.get(name) != expected
        ]
        if mismatches:
            raise RuntimeError(
                "resume integrity mismatch: " + ", ".join(sorted(mismatches))
            )
    else:
        checkpoint = {
            "schema_version": "1.0",
            "run_id": run_id,
            "started_at_utc": _utc_now(),
            "plan": asdict(plan),
            "plan_sha256": plan.sha256,
            "contract_sha256": contract_sha256,
            "acquisition_implementation_sha256": implementation_sha256,
            "external_prior_attempts": external_prior_attempts,
            "acquisition_conditions": {
                "api_version": "v2",
                "allowed_endpoints": [
                    "/markets/calendar",
                    "/equities/master",
                    "/equities/bars/daily",
                ],
                "provider_earliest_date": plan.provider_earliest_date,
                "frozen_end_date": plan.frozen_end_date,
                "annual_selection_years": list(range(2014, 2027)),
                "master_snapshot": "selection cutoff date",
                "ranking_window": "60 official JPX market sessions before selection",
                "history_scope": "selected candidate union plus frozen U15",
                "external_prior_attempts": external_prior_attempts,
                "remaining_hard_attempt_limit": (
                    plan.hard_attempt_limit - external_prior_attempts
                ),
                "credential_recorded": False,
            },
            "stage": "created",
            "fetched_candidate_codes": [],
            "rank_method": "four_session_range",
        }
    atomic_write_json(checkpoint_path, checkpoint)

    calendar_rows, _ = client.get_paginated(
        "/markets/calendar",
        {
            "from": plan.provider_earliest_date.replace("-", ""),
            "to": plan.frozen_end_date.replace("-", ""),
        },
        request_id="calendar-full-period",
        maximum_pages=1,
    )
    calendar = pd.DataFrame(calendar_rows)
    if not {"Date", "HolDiv"}.issubset(calendar.columns):
        raise RuntimeError("calendar schema mismatch")
    calendar["Date"] = pd.to_datetime(calendar["Date"]).dt.tz_localize(None)
    _write_frame(run_directory / "normalized" / "calendar.json", calendar)
    sessions = trading_sessions(calendar)
    expected_first = pd.Timestamp(plan.provider_earliest_date)
    expected_last = pd.Timestamp(plan.frozen_end_date)
    if (
        sessions.empty
        or sessions[0] != expected_first
        or sessions[-1] != expected_last
    ):
        raise RuntimeError(
            "calendar did not span the exact frozen provider period"
        )
    schedules = annual_selection_schedule(sessions)
    checkpoint["stage"] = "calendar"
    atomic_write_json(checkpoint_path, checkpoint)

    masters: dict[int, pd.DataFrame] = {}
    for schedule in schedules:
        rows, _ = client.get_paginated(
            "/equities/master",
            {"date": schedule.cutoff_date.replace("-", "")},
            request_id=f"master-{schedule.year}",
            maximum_pages=1,
        )
        master = normalize_master(rows)
        expected_master_date = pd.Timestamp(schedule.cutoff_date)
        if master.empty or set(master["Date"]) != {expected_master_date}:
            raise RuntimeError(
                "master response date did not match the frozen selection cutoff"
            )
        masters[schedule.year] = master
        _write_frame(
            run_directory / "normalized" / "masters" / f"{schedule.year}.json",
            master,
        )
    observed_products = sorted(
        {
            str(value).strip()
            for master in masters.values()
            for value in master["ProdCat"]
            if str(value).strip()
        }
    )
    if not any(
        value.upper() in DOMESTIC_EQUITY_PRODUCT_VALUES
        for value in observed_products
    ):
        raise RuntimeError(
            "frozen domestic-equity product category was absent from master snapshots"
        )
    checkpoint["stage"] = "masters"
    checkpoint["observed_product_category_count"] = len(observed_products)
    checkpoint["observed_product_category_set_sha256"] = canonical_sha256(observed_products)
    atomic_write_json(checkpoint_path, checkpoint)

    discovery_frames: list[pd.DataFrame] = []
    rank_method = str(checkpoint.get("rank_method", "four_session_range"))
    first_chunk = True
    for schedule in schedules:
        selection = pd.Timestamp(schedule.selection_date)
        position = int(sessions.searchsorted(selection))
        rank_dates = list(sessions[position - 60 : position])
        if rank_method == "four_session_range":
            for chunk_index, chunk in enumerate(_chunked(rank_dates, 4), start=1):
                try:
                    rows, _ = client.get_paginated(
                        "/equities/bars/daily",
                        {
                            "from": chunk[0].strftime("%Y%m%d"),
                            "to": chunk[-1].strftime("%Y%m%d"),
                        },
                        request_id=f"rank-{schedule.year}-chunk-{chunk_index:02d}",
                        maximum_pages=2,
                    )
                except (HttpStatusError, ResponseTooLarge) as exc:
                    fallback_allowed = isinstance(exc, ResponseTooLarge) or (
                        isinstance(exc, HttpStatusError)
                        and exc.status in {400, 413, 422}
                    )
                    if first_chunk and fallback_allowed:
                        rank_method = "single_session_no_retry"
                        checkpoint["rank_method"] = rank_method
                        checkpoint["rank_fallback_reason"] = (
                            "local_response_size_cap"
                            if isinstance(exc, ResponseTooLarge)
                            else f"http_{exc.status}"
                        )
                        atomic_write_json(checkpoint_path, checkpoint)
                        discovery_frames.clear()
                        break
                    raise
                frame = normalize_bars(rows)
                observed_dates = set(frame["Date"])
                if not set(chunk).issubset(observed_dates):
                    raise RuntimeError("rank range response omitted an expected JPX session")
                discovery_frames.append(frame.loc[frame["Date"].isin(chunk)])
                first_chunk = False
            if rank_method != "four_session_range":
                break
        else:
            break

    if rank_method == "single_session_no_retry":
        discovery_frames.clear()
        for schedule in schedules:
            selection = pd.Timestamp(schedule.selection_date)
            position = int(sessions.searchsorted(selection))
            rank_dates = list(sessions[position - 60 : position])
            for session in rank_dates:
                rows, _ = client.get_paginated(
                    "/equities/bars/daily",
                    {"date": session.strftime("%Y%m%d")},
                    request_id=f"rank-date-{session.strftime('%Y%m%d')}",
                    maximum_pages=1,
                    maximum_retries=0,
                )
                frame = normalize_bars(rows)
                if session not in set(frame["Date"]):
                    raise RuntimeError("rank date response omitted the requested JPX session")
                discovery_frames.append(frame.loc[frame["Date"] == session])

    discovery = (
        pd.concat(discovery_frames, ignore_index=True)
        .drop_duplicates(["Date", "Code"], keep="last")
        .sort_values(["Code", "Date"], ignore_index=True)
    )
    _write_frame(run_directory / "normalized" / "rank_discovery.json", discovery)
    checkpoint["stage"] = "rank_discovery"
    checkpoint["rank_method"] = rank_method
    atomic_write_json(checkpoint_path, checkpoint)

    preliminary: dict[int, list[dict[str, Any]]] = {
        schedule.year: _preliminary_rank(
            masters[schedule.year],
            discovery,
            sessions,
            schedule,
        )
        for schedule in schedules
    }
    schedule_by_year = {item.year: item for item in schedules}
    pointers = {year: 0 for year in preliminary}
    available_bars: dict[str, pd.DataFrame] = {}
    fetched_dynamic: set[str] = set(checkpoint.get("fetched_candidate_codes", []))
    for code in sorted(fetched_dynamic):
        validate_security_code(code)
        available_bars[code] = _load_code_bars(run_directory, code)
    evaluations: dict[int, dict[str, Any]] = {}

    while True:
        unfinished: list[int] = []
        for year in sorted(preliminary):
            processed = preliminary[year][: pointers[year]]
            evaluation = _evaluate_year(
                year,
                schedule_by_year[year],
                masters[year],
                processed,
                available_bars,
                sessions,
            )
            evaluations[year] = evaluation
            if not _year_done(preliminary[year], pointers[year], evaluation):
                unfinished.append(year)
        if not unfinished:
            break
        progressed = False
        for year in unfinished:
            if pointers[year] >= len(preliminary[year]):
                continue
            item = preliminary[year][pointers[year]]
            pointers[year] += 1
            code = str(item["code"])
            progressed = True
            if code in available_bars:
                continue
            if len(fetched_dynamic) >= plan.candidate_frontier_cap:
                raise RuntimeError("candidate frontier cap reached before all years resolved")
            rows, _ = client.get_paginated(
                "/equities/bars/daily",
                {
                    "code": code,
                    "from": plan.provider_earliest_date.replace("-", ""),
                    "to": plan.frozen_end_date.replace("-", ""),
                },
                request_id=f"history-{code}",
                maximum_pages=plan.candidate_page_cap,
            )
            frame = normalize_bars(rows)
            if frame.empty or set(frame["Code"]) != {code}:
                raise RuntimeError("code history response did not match the requested code")
            available_bars[code] = frame
            fetched_dynamic.add(code)
            _write_frame(
                run_directory / "normalized" / "bars" / f"{code}.json",
                frame,
            )
            checkpoint["fetched_candidate_codes"] = sorted(fetched_dynamic)
            checkpoint["candidate_count"] = len(fetched_dynamic)
            checkpoint["pointers"] = {str(key): value for key, value in pointers.items()}
            checkpoint["stage"] = "candidate_histories"
            atomic_write_json(checkpoint_path, checkpoint)
        if not progressed:
            raise RuntimeError("candidate acquisition made no progress")

    # Re-evaluate after the final pointer advance.
    for year in sorted(preliminary):
        evaluations[year] = _evaluate_year(
            year,
            schedule_by_year[year],
            masters[year],
            preliminary[year][: pointers[year]],
            available_bars,
            sessions,
        )

    for code in load_u15_codes():
        if code in available_bars:
            continue
        path = run_directory / "normalized" / "bars" / f"{code}.json"
        if path.is_file():
            available_bars[code] = _load_code_bars(run_directory, code)
            continue
        rows, _ = client.get_paginated(
            "/equities/bars/daily",
            {
                "code": code,
                "from": plan.provider_earliest_date.replace("-", ""),
                "to": plan.frozen_end_date.replace("-", ""),
            },
            request_id=f"u15-history-{code}",
            maximum_pages=plan.candidate_page_cap,
        )
        frame = normalize_bars(rows)
        if frame.empty or set(frame["Code"]) != {code}:
            raise RuntimeError("U15 history response did not match the requested code")
        available_bars[code] = frame
        _write_frame(path, frame)

    membership: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "classification": CONTRACT["classification"],
        "U15_ADJUSTED_STATIC": load_u15_codes(),
        "U15_RAW_COMMON_PERIOD": load_u15_codes(),
        "U50_PIT_LITE": {},
        "U100_PIT_LITE": {},
    }
    aggregate_rows: list[dict[str, Any]] = []
    for year in sorted(evaluations):
        result = evaluations[year]
        selected_50 = result["u50_selected"]
        selected_100 = result["u100_selected"]
        membership["U50_PIT_LITE"][str(year)] = [
            item.code for item in selected_50
        ]
        membership["U100_PIT_LITE"][str(year)] = [
            item.code for item in selected_100
        ]
        aggregate_rows.extend(
            [
                selection_aggregate(
                    "U50_PIT_LITE",
                    schedule_by_year[year],
                    result["u50_candidates"],
                    selected_50,
                    U50_TARGET,
                    evaluated_frontier_count=pointers[year],
                ),
                selection_aggregate(
                    "U100_PIT_LITE",
                    schedule_by_year[year],
                    result["u100_candidates"],
                    selected_100,
                    U100_TARGET,
                    evaluated_frontier_count=pointers[year],
                ),
            ]
        )
    atomic_write_json(
        run_directory / "universe_membership" / "annual_membership.json",
        membership,
    )
    atomic_write_json(
        run_directory / "universe_membership" / "aggregate_counts.json",
        aggregate_rows,
    )
    audit = client.sanitized_audit()
    audit.update(
        {
            "run_id": run_id,
            "plan_sha256": plan.sha256,
            "estimated_expected_attempts": (
                1310 if rank_method == "single_session_no_retry" else plan.expected_attempts
            ),
            "planned_worst_case_attempts": (
                2373
                if rank_method == "single_session_no_retry"
                else plan.planned_worst_case_attempts
            ),
            "rank_method": rank_method,
            "candidate_histories": len(fetched_dynamic),
            "raw_licensed_data_committed": False,
            "external_prior_attempts": external_prior_attempts,
            "gate_attempts_used": external_prior_attempts + audit["attempts_used"],
        }
    )
    atomic_write_json(run_directory / "checkpoint" / "request_audit.json", audit)
    checkpoint["stage"] = "complete"
    checkpoint["completed_at_utc"] = _utc_now()
    checkpoint["request_audit_sha256"] = canonical_sha256(audit)
    atomic_write_json(checkpoint_path, checkpoint)
    manifest = build_deletion_manifest(run_id, run_directory)
    cleanup_source = Path(__file__).resolve().parents[2] / "scripts" / "cleanup_private_data.py"
    atomic_write_bytes(
        run_directory.parents[1] / "cleanup_private_data.py",
        cleanup_source.read_bytes(),
    )
    return {
        "run_id": run_id,
        "stage": "complete",
        "attempts_used": audit["attempts_used"],
        "gate_attempts_used": audit["gate_attempts_used"],
        "candidate_histories": len(fetched_dynamic),
        "rank_method": rank_method,
        "manifest_entries": len(manifest["entries"]),
        "u50_shortfall_years": sum(
            len(evaluations[year]["u50_selected"]) < U50_TARGET
            for year in evaluations
        ),
        "u100_shortfall_years": sum(
            len(evaluations[year]["u100_selected"]) < U100_TARGET
            for year in evaluations
        ),
    }
