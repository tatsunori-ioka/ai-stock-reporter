#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


LAB_ROOT = Path(__file__).resolve().parent
REPO_ROOT = LAB_ROOT.parents[1]
SRC_ROOT = LAB_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tgs_stable_v2.artifacts import (  # noqa: E402
    markdown_table,
    number,
    percent,
    sha256_file,
    write_csv,
    write_json,
)
from tgs_stable_v2.backtest import raw_signal_events, simulate_universe  # noqa: E402
from tgs_stable_v2.config import (  # noqa: E402
    BASE_COMMIT,
    COST_SCENARIOS,
    MODEL_ID,
)
from tgs_stable_v2.data import (  # noqa: E402
    availability_rows,
    download_daily_data,
    maximum_common_window,
)
from tgs_stable_v2.indicators import build_signal_frame  # noqa: E402
from tgs_stable_v2.metrics import (  # noqa: E402
    equal_notional_equity,
    longest_no_signal_period,
    portfolio_metrics,
    trade_metrics,
)


RESULTS = LAB_ROOT / "results"
REPORTS = LAB_ROOT / "reports"
DATA_MANIFEST = LAB_ROOT / "data_manifest"
CONTRACT_PATH = LAB_ROOT / "contracts" / "ver1_baseline_contract.json"
U15_CONFIG_PATH = LAB_ROOT / "config" / "universe_u15.yaml"
PROPOSAL_PATHS = [
    LAB_ROOT / "config" / "universe_u50_proposal.yaml",
    LAB_ROOT / "config" / "universe_u100_proposal.yaml",
]
RESULT_CLASSIFICATION = "survivorship-biased exploratory evidence; not Formal Candidate"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the frozen, research-only U15 baseline.")
    parser.add_argument("--start", default="1990-01-01")
    parser.add_argument("--end-exclusive", default="2026-07-27")
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_production_hashes(contract: dict[str, Any]) -> dict[str, str]:
    actual: dict[str, str] = {}
    mismatches: list[str] = []
    for relative, expected in contract["production_sha256"].items():
        source = REPO_ROOT / relative
        if not source.exists():
            mismatches.append(f"{relative}: missing")
            continue
        digest = sha256_file(source)
        actual[relative] = digest
        if digest != expected:
            mismatches.append(f"{relative}: expected {expected}, got {digest}")
    if mismatches:
        raise RuntimeError("production freeze verification failed:\n" + "\n".join(mismatches))
    return actual


def research_implementation_hashes() -> dict[str, str]:
    paths = [
        LAB_ROOT / "run_u15.py",
        LAB_ROOT / "requirements.txt",
        *sorted((LAB_ROOT / "src").rglob("*.py")),
        *sorted((LAB_ROOT / "tests").rglob("*.py")),
    ]
    return {
        str(path.relative_to(LAB_ROOT)): sha256_file(path)
        for path in paths
    }


def build_metadata(config: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, str]]]:
    rows = config["tickers"]
    tickers = [row["ticker"] for row in rows]
    metadata = {row["ticker"]: row for row in rows}
    return tickers, metadata


def market_dates_between(
    signal_frames: dict[str, pd.DataFrame],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(
        sorted(
            {
                pd.Timestamp(value)
                for frame in signal_frames.values()
                for value in frame.index
                if start <= pd.Timestamp(value) <= end
            }
        )
    )


def chronological_splits(market_dates: pd.DatetimeIndex) -> dict[str, dict[str, Any]]:
    count = len(market_dates)
    if count < 5:
        raise RuntimeError("not enough effective sessions for chronological splits")
    development_end = max(0, int(count * 0.60) - 1)
    validation_end = max(development_end + 1, int(count * 0.80) - 1)
    return {
        "development": {
            "start": market_dates[0].date().isoformat(),
            "end": market_dates[development_end].date().isoformat(),
            "sessions": development_end + 1,
        },
        "validation": {
            "start": market_dates[development_end + 1].date().isoformat(),
            "end": market_dates[validation_end].date().isoformat(),
            "sessions": validation_end - development_end,
        },
        "final_holdout": {
            "start": market_dates[validation_end + 1].date().isoformat(),
            "end": market_dates[-1].date().isoformat(),
            "sessions": count - validation_end - 1,
            "used_for_optimization": False,
        },
    }


def flatten_metrics(trades: pd.DataFrame, curve: pd.DataFrame) -> dict[str, Any]:
    return {**trade_metrics(trades), **portfolio_metrics(curve)}


def label_result(frame: pd.DataFrame, run_id: str) -> pd.DataFrame:
    result = frame.copy()
    labels = {
        "run_id": run_id,
        "model_id": MODEL_ID,
        "universe_id": "U15",
        "base_commit": BASE_COMMIT,
        "point_in_time_universe": False,
        "survivorship_bias": True,
        "classification": RESULT_CLASSIFICATION,
    }
    for column in labels:
        if column in result.columns:
            result = result.drop(columns=[column])
    for column, value in reversed(list(labels.items())):
        result.insert(0, column, value)
    return result


def slice_curve(curve: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    dates = pd.to_datetime(curve["date"])
    return curve.loc[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))].copy()


def yearly_table(
    primary_trades: pd.DataFrame,
    signals: pd.DataFrame,
    curve: pd.DataFrame,
    evaluation_start: pd.Timestamp,
    evaluation_end: pd.Timestamp,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    signal_dates = pd.to_datetime(signals["signal_date"])
    trade_signal_dates = (
        pd.to_datetime(primary_trades["signal_date"])
        if not primary_trades.empty
        else pd.Series(dtype="datetime64[ns]")
    )
    trade_exit_dates = (
        pd.to_datetime(primary_trades["exit_date"])
        if not primary_trades.empty
        else pd.Series(dtype="datetime64[ns]")
    )
    curve_dates = pd.to_datetime(curve["date"])
    for year in range(evaluation_start.year, evaluation_end.year + 1):
        year_signals = signals.loc[signal_dates.dt.year == year]
        signal_cohort = (
            primary_trades.loc[trade_signal_dates.dt.year == year]
            if not primary_trades.empty
            else primary_trades
        )
        year_trades = (
            primary_trades.loc[trade_exit_dates.dt.year == year]
            if not primary_trades.empty
            else primary_trades
        )
        current_curve = curve.loc[curve_dates.dt.year == year]
        prior_curve = curve.loc[curve_dates < pd.Timestamp(f"{year}-01-01")].tail(1)
        year_curve = pd.concat([prior_curve, current_curve], ignore_index=True)
        metrics = flatten_metrics(year_trades, year_curve)
        current_year_portfolio = portfolio_metrics(current_curve)
        metrics["market_exposure"] = current_year_portfolio["market_exposure"]
        metrics["maximum_concurrent_positions"] = current_year_portfolio[
            "maximum_concurrent_positions"
        ]
        rows.append(
            {
                "year": year,
                "signal_count": len(year_signals),
                "signal_cohort_trade_count": len(signal_cohort),
                "trade_metric_basis": "exit_year",
                "portfolio_metric_basis": "calendar_year_with_prior_close_anchor",
                "exposure_metric_basis": "calendar_year_sessions_only",
                **metrics,
            }
        )
    return pd.DataFrame(rows)


def monthly_signal_table(
    signals: pd.DataFrame,
    trades: pd.DataFrame,
    market_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    signal_dates = pd.to_datetime(signals["signal_date"])
    trade_dates = pd.to_datetime(trades["signal_date"]) if not trades.empty else pd.Series(dtype="datetime64[ns]")
    rows: list[dict[str, Any]] = []
    periods = pd.period_range(market_dates[0].to_period("M"), market_dates[-1].to_period("M"), freq="M")
    for period in periods:
        period_sessions = market_dates[market_dates.to_period("M") == period]
        period_signals = signals.loc[signal_dates.dt.to_period("M") == period]
        period_trades = trades.loc[trade_dates.dt.to_period("M") == period] if not trades.empty else trades
        signal_session_count = pd.to_datetime(period_signals["signal_date"]).nunique() if not period_signals.empty else 0
        rows.append(
            {
                "year_month": str(period),
                "market_sessions": len(period_sessions),
                "raw_signal_count": len(period_signals),
                "eligible_trade_count": len(period_trades),
                "unique_tickers": period_signals["ticker"].nunique() if not period_signals.empty else 0,
                "zero_signal_sessions": len(period_sessions) - signal_session_count,
            }
        )
    return pd.DataFrame(rows)


def score_bucket_table(signals: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for score in [90, 100, 110, 120]:
        bucket_signals = signals.loc[pd.to_numeric(signals["score"]) == score]
        bucket_trades = trades.loc[pd.to_numeric(trades["score"]) == score] if not trades.empty else trades
        rows.append(
            {
                "score_bucket": score,
                "signal_count": len(bucket_signals),
                **trade_metrics(bucket_trades),
            }
        )
    return pd.DataFrame(rows)


def ticker_table(
    signals: pd.DataFrame,
    trades: pd.DataFrame,
    metadata: dict[str, dict[str, str]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for ticker in sorted(metadata):
        ticker_signals = signals.loc[signals["ticker"] == ticker]
        ticker_trades = trades.loc[trades["ticker"] == ticker] if not trades.empty else trades
        rows.append(
            {
                "ticker": ticker,
                "name": metadata[ticker].get("name", ""),
                "sector": metadata[ticker].get("sector", ""),
                "signal_count": len(ticker_signals),
                **trade_metrics(ticker_trades),
            }
        )
    return pd.DataFrame(rows)


def sector_table(signals: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    sectors = sorted(set(signals["sector"]) | set(trades["sector"] if not trades.empty else []))
    for sector in sectors:
        sector_signals = signals.loc[signals["sector"] == sector]
        sector_trades = trades.loc[trades["sector"] == sector] if not trades.empty else trades
        rows.append(
            {
                "sector": sector,
                "signal_count": len(sector_signals),
                **trade_metrics(sector_trades),
            }
        )
    return pd.DataFrame(rows)


def split_table(
    signals: pd.DataFrame,
    trades: pd.DataFrame,
    splits: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    signal_dates = pd.to_datetime(signals["signal_date"])
    trade_dates = pd.to_datetime(trades["signal_date"]) if not trades.empty else pd.Series(dtype="datetime64[ns]")
    rows: list[dict[str, Any]] = []
    for name, split in splits.items():
        start = pd.Timestamp(split["start"])
        end = pd.Timestamp(split["end"])
        selected_signals = signals.loc[(signal_dates >= start) & (signal_dates <= end)]
        cohort = trades.loc[(trade_dates >= start) & (trade_dates <= end)] if not trades.empty else trades
        completed_in_split = (
            cohort.loc[pd.to_datetime(cohort["exit_date"]) <= end]
            if not cohort.empty
            else cohort
        )
        rows.append(
            {
                "split": name,
                "start": split["start"],
                "end": split["end"],
                "sessions": split["sessions"],
                "signal_count": len(selected_signals),
                "accepted_cohort_trade_count": len(cohort),
                "cross_boundary_excluded": len(cohort) - len(completed_in_split),
                **trade_metrics(completed_in_split),
            }
        )
    return pd.DataFrame(rows)


def display_sensitivity(frame: pd.DataFrame, key: str) -> pd.DataFrame:
    columns = [
        key,
        "trade_count",
        "closed_trade_count",
        "total_return",
        "cagr",
        "maximum_drawdown",
        "profit_factor",
        "win_rate",
        "expectancy_per_trade",
    ]
    shown = frame[columns].copy()
    for column in ["total_return", "cagr", "maximum_drawdown", "win_rate", "expectancy_per_trade"]:
        shown[column] = shown[column].map(percent)
    shown["profit_factor"] = shown["profit_factor"].map(number)
    return shown


def write_data_availability_report(
    manifest: dict[str, Any],
    availability: pd.DataFrame,
) -> None:
    table = availability[
        [
            "ticker",
            "first_date",
            "last_date",
            "rows",
            "missing_vs_union_sessions",
            "duplicate_dates",
            "nonpositive_ohlc_rows_removed",
            "nonpositive_volume_rows_removed",
        ]
    ]
    text = f"""# TGS Stable Ver2.0 Data Availability Report

## Decision

U15 data is available for a long exploratory baseline, but the repository
cannot construct a point-in-time universe. The result is therefore
**survivorship-biased exploratory evidence** and is not a Formal Candidate.

## Acquisition

- Provider: {manifest["provider"]["provider"]}
- yfinance: `{manifest["provider"]["yfinance_version"]}`
- pandas: `{manifest["provider"]["pandas_version"]}`
- Request: `{manifest["request"]["start"]}` through
  `{manifest["request"]["end_exclusive"]}` (end-exclusive)
- `auto_adjust=False`; indicators and fills use raw OHLCV.
- Raw cache committed: no
- Raw normalized data hash recorded per ticker: yes
- Same-cache rerun: deterministic
- Fresh-download caveat: Yahoo history is mutable; hashes detect drift but the
  ignored cache cannot reconstruct a prior snapshot.

## Period and warm-up

- Maximum common raw window: `{manifest["period"]["maximum_common_start"]}`
  through `{manifest["period"]["maximum_common_end"]}`
- Effective test window after common indicator warm-up:
  `{manifest["period"]["effective_start"]}` through
  `{manifest["period"]["effective_end"]}`
- Warm-up rule: all required inputs ready, dominated by the 200-week SMA.
- Warm-up rows are excluded from performance.

## Ticker coverage

{markdown_table(table)}

## Adjustment and corporate actions

Ver1.0 explicitly requests unadjusted data and discards `Adj Close` from its
calculation. The research baseline reproduces that behavior. `Adj Close` is
retained only to audit ratio changes. There is no split/dividend/merger action
table in the repository, and shares are not transformed for a corporate
action. Long-horizon results may therefore contain corporate-action
distortions and exclude dividend total return.

## Missing data and tradeability

- A row missing any Open/High/Low/Close/Volume value is removed.
- Nonpositive OHLC or `Volume <= 0` is treated as a non-trading/provider
  placeholder and excluded before indicators, sessions, fills and holding-day
  counts; removed counts are shown above.
- A signal without a bar on the immediately following union-market session is
  unfilled rather than delayed.
- Holding sessions count observed ticker bars, including entry day.
- A position unresolved at the data boundary is marked to its final available
  Close, flagged right-censored, and excluded from closed-trade statistics.
- Yahoo data cannot distinguish provider lag, holiday, suspension, delisting,
  or ticker change without an external event master.

## Listings, delistings and point-in-time status

`stable_universe_metadata.csv` is an undated current snapshot. It has no
listing interval, delisting status, historical sector, historical market cap,
corporate group, or ticker lineage. Applying today's surviving U15 backward
creates survivorship and selection look-ahead. A Formal Candidate requires
dated issue masters and dated universe inputs.

## J-Quants audit

No J-Quants client, endpoint, dependency, token handling, or Premium-specific
code exists in the repository. No J-Quants API call was made. Whether a
particular paid plan supplies every required point-in-time field remains
unverified and is not assumed.

## Local-data audit

Before this research run, the worktree contained only the 225-row undated
universe metadata CSV and the 15-row watchlist CSV. It contained no OHLC
history, database, Parquet file, or reusable price cache.
"""
    (DATA_MANIFEST / "DATA_AVAILABILITY_REPORT.md").write_text(text, encoding="utf-8")


def write_u15_report(
    summary: dict[str, Any],
    cost_table: pd.DataFrame,
    path_table: pd.DataFrame,
    score_table: pd.DataFrame,
    ticker_metrics: pd.DataFrame,
    sector_metrics: pd.DataFrame,
    split_metrics: pd.DataFrame,
) -> None:
    headline = summary["headline"]
    trades = summary["trade_metrics"]
    no_signal = summary["longest_no_signal_period"]
    cost_display = display_sensitivity(cost_table, "scenario")
    path_display = display_sensitivity(path_table, "path_policy")
    score_display = score_table[
        ["score_bucket", "signal_count", "trade_count", "closed_trade_count", "profit_factor", "win_rate", "expectancy_per_trade"]
    ].copy()
    score_display["win_rate"] = score_display["win_rate"].map(percent)
    score_display["expectancy_per_trade"] = score_display["expectancy_per_trade"].map(percent)
    score_display["profit_factor"] = score_display["profit_factor"].map(number)

    ticker_display = ticker_metrics[
        ["ticker", "sector", "signal_count", "trade_count", "closed_trade_count", "profit_factor", "win_rate", "expectancy_per_trade"]
    ].copy()
    ticker_display["win_rate"] = ticker_display["win_rate"].map(percent)
    ticker_display["expectancy_per_trade"] = ticker_display["expectancy_per_trade"].map(percent)
    ticker_display["profit_factor"] = ticker_display["profit_factor"].map(number)

    sector_display = sector_metrics[
        ["sector", "signal_count", "trade_count", "closed_trade_count", "profit_factor", "win_rate", "expectancy_per_trade"]
    ].copy()
    sector_display["win_rate"] = sector_display["win_rate"].map(percent)
    sector_display["expectancy_per_trade"] = sector_display["expectancy_per_trade"].map(percent)
    sector_display["profit_factor"] = sector_display["profit_factor"].map(number)

    split_display = split_metrics[
        [
            "split",
            "start",
            "end",
            "sessions",
            "signal_count",
            "accepted_cohort_trade_count",
            "cross_boundary_excluded",
            "trade_count",
            "profit_factor",
            "win_rate",
            "expectancy_per_trade",
        ]
    ].copy()
    split_display["win_rate"] = split_display["win_rate"].map(percent)
    split_display["expectancy_per_trade"] = split_display["expectancy_per_trade"].map(percent)
    split_display["profit_factor"] = split_display["profit_factor"].map(number)

    text = f"""# TGS Stable Ver2.0 U15 Baseline Report

Model ID: `{MODEL_ID}`

Run ID: `{summary["run_id"]}`

Base commit: `{BASE_COMMIT}`

## Gate classification

This is **survivorship-biased exploratory evidence**, not a Formal Candidate.
The current 15-name snapshot was applied backward because no point-in-time
issue master exists. No parameter was optimized, and U50/U100 were not run.

## Frozen setup

- Data: yfinance raw daily OHLCV, `auto_adjust=False`
- Period: `{summary["period"]["effective_start"]}` through
  `{summary["period"]["effective_end"]}`
- Warm-up: strict full-indicator readiness, dominated by 200 weekly bars
- Formal path: basic cost + conservative same-bar ordering
- Entry: next market session Open
- Exit: -10% stop, +30% take profit, or 60th session Close
- Portfolio: fixed equal-notional, all accepted trades, no selection or leverage

The execution layer is the V2 research overlay required by this gate. It
freezes Ver1 direction, next-session entry and -10%/+30%/60-session parameters,
but adds the mandated gap fills, cost scenarios, missing-bar rule and path
sensitivity. It is not a byte-for-byte replay of the dormant Ver1 paper ledger.

## Headline — basic + conservative

- Total return: {percent(headline["total_return"])}
- CAGR: {percent(headline["cagr"])}
- Maximum drawdown: {percent(headline["maximum_drawdown"])}
- Calmar ratio: {number(headline["calmar_ratio"])}
- Profit factor: {number(trades["profit_factor"])}
- Win rate: {percent(trades["win_rate"])}
- Average win: {percent(trades["average_win"])}
- Average loss: {percent(trades["average_loss"])}
- Payoff ratio: {number(trades["payoff_ratio"])}
- Expectancy per closed trade: {percent(trades["expectancy_per_trade"])}
- Accepted trades: {trades["trade_count"]} ({trades["closed_trade_count"]} closed,
  {trades["open_trade_count"]} right-censored)
- Raw signal events: {summary["signal_metrics"]["raw_signal_count"]}
- Annual signal frequency: {summary["signal_metrics"]["annual_signal_frequency"]:.2f}
- Longest no-signal interval: {no_signal["sessions"]} market sessions /
  {no_signal["calendar_days"]} calendar days
  (`{no_signal["start"]}` to `{no_signal["end"]}`)
- Maximum consecutive losses: {trades["max_consecutive_losses"]}
- Average / median holding: {number(trades["average_holding_sessions"])} /
  {number(trades["median_holding_sessions"])} sessions
- Market exposure: {percent(headline["market_exposure"])}
- Maximum simultaneous positions: {headline["maximum_concurrent_positions"]}

`total return`, CAGR, drawdown, Calmar, exposure and concurrency are from the
separate fixed equal-notional portfolio. This is a mechanical, ex-post
capacity-normalized comparison overlay, not an investable portfolio return.
Profit factor, win rate, payoff and expectancy use closed independent trades.
Right-censored trades are marked to the final Close in portfolio equity but
excluded from closed-trade statistics. Exposure and concurrency conservatively
count an exit date as occupied for that entire market session, including an
Open exit.

## Cost sensitivity

{markdown_table(cost_display)}

## Conservative / optimistic path sensitivity

{markdown_table(path_display)}

Headline total-return difference (optimistic minus conservative):
{percent(summary["path_difference"]["total_return_delta"])}. Expectancy
difference: {percent(summary["path_difference"]["expectancy_delta"])}.

## Score buckets

{markdown_table(score_display)}

The 110 bucket is deliberately present and empty because 110 is unreachable
under the frozen 30/30/20/20/20 weights.

## Ticker concentration and results

{markdown_table(ticker_display)}

Top ticker share of accepted trades:
{percent(summary["concentration"]["top_ticker_trade_share"])}.

## Sector concentration and results

{markdown_table(sector_display)}

Top sector share of accepted trades:
{percent(summary["concentration"]["top_sector_trade_share"])}.

## Chronological split

{markdown_table(split_display)}

The split is 60% development, 20% validation and 20% final holdout by effective
market sessions. These are closed independent-trade cohort statistics, not
split-level portfolio return or drawdown. Split metrics exclude any
signal-cohort trade that exits after that split's boundary; the excluded count
is shown explicitly. The rule was already frozen, and final holdout prices were
not used in development or validation metrics or for optimization.

Annual portfolio returns use each prior calendar year's final equity as the
opening anchor. Annual exposure and concurrency use current-year sessions only.
Annual trade statistics are grouped by exit year; the signal-cohort count is
reported separately.

## Robustness and limitations

- The score and weekly calculations are regression-tested against the
  production implementation.
- Full-history vs truncated-history look-ahead checks are included.
- Corporate actions are not adjusted because Ver1.0 uses raw OHLCV. Dividend
  total return is absent, and split/merger distortions remain possible.
- yfinance alone cannot certify delistings, suspensions or ticker lineage.
- Current-snapshot survivorship bias is decisive: these numbers cannot justify
  a Formal Candidate or production change.
- The equal-notional portfolio is a mechanical comparison layer, not an
  optimized capital allocation.
- Re-running from the same ignored cache is deterministic. A fresh clone must
  re-download mutable Yahoo history, so exact reconstruction of this snapshot
  requires a separately licensed/versioned raw-data archive.

## Reproduce

```bash
PYTHONPATH=research/tgs_stable_v2/src \\
python3 -m pytest research/tgs_stable_v2/tests -q

PYTHONPATH=research/tgs_stable_v2/src \\
python3 research/tgs_stable_v2/run_u15.py
```

The canonical detailed outputs are in `research/tgs_stable_v2/results/`.
"""
    (REPORTS / "U15_BASELINE_REPORT.md").write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    contract = read_json(CONTRACT_PATH)
    if contract["repository_base_commit"] != BASE_COMMIT:
        raise RuntimeError("contract/base commit mismatch")
    production_hashes = verify_production_hashes(contract)
    u15_config = read_json(U15_CONFIG_PATH)
    tickers, metadata = build_metadata(u15_config)
    if tickers != contract["universe"]["tickers"]:
        raise RuntimeError("U15 config does not match the frozen contract")
    proposal_hashes = {
        str(path.relative_to(LAB_ROOT)): sha256_file(path)
        for path in PROPOSAL_PATHS
    }
    if proposal_hashes != contract["universe_proposals_sha256"]:
        raise RuntimeError("U50/U100 proposal hash does not match the pre-result contract")

    frames, provider = download_daily_data(
        tickers,
        start=args.start,
        end=args.end_exclusive,
        cache_dir=LAB_ROOT / "data" / "cache",
        refresh=args.refresh,
    )
    availability = pd.DataFrame(availability_rows(frames))
    signal_frames = {ticker: build_signal_frame(frame) for ticker, frame in frames.items()}
    common_start, common_end = maximum_common_window(frames)
    ready_dates = {
        ticker: frame.index[frame["indicator_ready"]][0]
        for ticker, frame in signal_frames.items()
        if frame["indicator_ready"].any()
    }
    if len(ready_dates) != len(tickers):
        missing = sorted(set(tickers) - set(ready_dates))
        raise RuntimeError(f"indicator warm-up never completed for: {missing}")
    evaluation_start = max(common_start, *ready_dates.values())
    evaluation_end = common_end
    market_dates = market_dates_between(signal_frames, evaluation_start, evaluation_end)
    splits = chronological_splits(market_dates)
    signals = raw_signal_events(
        signal_frames,
        metadata,
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
    )

    scenario_trades: dict[tuple[str, str], pd.DataFrame] = {}
    scenario_counters: dict[tuple[str, str], dict[str, int]] = {}
    scenario_curves: dict[tuple[str, str], pd.DataFrame] = {}
    for scenario_name, cost in COST_SCENARIOS.items():
        trades, counters = simulate_universe(
            signal_frames,
            metadata,
            model_id=MODEL_ID,
            universe_id="U15",
            evaluation_start=evaluation_start,
            evaluation_end=evaluation_end,
            cost=cost,
            path_policy="conservative",
        )
        scenario_trades[(scenario_name, "conservative")] = trades
        scenario_counters[(scenario_name, "conservative")] = counters
        scenario_curves[(scenario_name, "conservative")] = equal_notional_equity(
            trades,
            signal_frames,
            evaluation_start=evaluation_start,
            evaluation_end=evaluation_end,
        )

    optimistic_trades, optimistic_counters = simulate_universe(
        signal_frames,
        metadata,
        model_id=MODEL_ID,
        universe_id="U15",
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
        cost=COST_SCENARIOS["basic"],
        path_policy="optimistic",
    )
    scenario_trades[("basic", "optimistic")] = optimistic_trades
    scenario_counters[("basic", "optimistic")] = optimistic_counters
    scenario_curves[("basic", "optimistic")] = equal_notional_equity(
        optimistic_trades,
        signal_frames,
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
    )

    primary_trades = scenario_trades[("basic", "conservative")]
    primary_curve = scenario_curves[("basic", "conservative")]
    primary_trade_metrics = trade_metrics(primary_trades)
    headline = portfolio_metrics(primary_curve)

    cost_rows: list[dict[str, Any]] = []
    for scenario_name, cost in COST_SCENARIOS.items():
        trades = scenario_trades[(scenario_name, "conservative")]
        curve = scenario_curves[(scenario_name, "conservative")]
        cost_rows.append(
            {
                "scenario": scenario_name,
                "commission_bps_per_side": cost.commission_bps_per_side,
                "slippage_bps_per_side": cost.slippage_bps_per_side,
                "round_trip_bps": cost.round_trip_bps,
                **flatten_metrics(trades, curve),
            }
        )
    cost_table = pd.DataFrame(cost_rows)

    path_rows: list[dict[str, Any]] = []
    for path_policy in ["conservative", "optimistic"]:
        trades = scenario_trades[("basic", path_policy)]
        curve = scenario_curves[("basic", path_policy)]
        path_rows.append(
            {
                "path_policy": path_policy,
                "same_bar_both_trade_count": int(
                    trades["exit_reason"].str.startswith("stop_and_take_same_day").sum()
                )
                if not trades.empty
                else 0,
                **flatten_metrics(trades, curve),
            }
        )
    path_table = pd.DataFrame(path_rows)

    yearly = yearly_table(primary_trades, signals, primary_curve, evaluation_start, evaluation_end)
    monthly = monthly_signal_table(signals, primary_trades, market_dates)
    score_buckets = score_bucket_table(signals, primary_trades)
    ticker_metrics = ticker_table(signals, primary_trades, metadata)
    sector_metrics = sector_table(signals, primary_trades)
    split_metrics = split_table(signals, primary_trades, splits)
    longest_gap = longest_no_signal_period(signals, market_dates)

    top_ticker_share = (
        float(ticker_metrics["trade_count"].max() / primary_trade_metrics["trade_count"])
        if primary_trade_metrics["trade_count"]
        else 0.0
    )
    top_sector_share = (
        float(sector_metrics["trade_count"].max() / primary_trade_metrics["trade_count"])
        if primary_trade_metrics["trade_count"]
        else 0.0
    )
    effective_years = max(
        (evaluation_end - evaluation_start).days / 365.2425,
        1 / 365.2425,
    )

    fingerprint = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "u15_config_sha256": sha256_file(U15_CONFIG_PATH),
        "raw_sha256": dict(zip(availability["ticker"], availability["raw_sha256"])),
        "universe_proposals_sha256": proposal_hashes,
        "research_implementation_sha256": research_implementation_hashes(),
        "base_commit": BASE_COMMIT,
    }
    run_id = hashlib.sha256(
        json.dumps(fingerprint, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]

    conservative_row = path_table.loc[path_table["path_policy"] == "conservative"].iloc[0]
    optimistic_row = path_table.loc[path_table["path_policy"] == "optimistic"].iloc[0]
    data_manifest = {
        "schema_version": 1,
        "model_id": MODEL_ID,
        "run_id": run_id,
        "base_commit": BASE_COMMIT,
        "provider": {
            key: provider[key]
            for key in ["provider", "yfinance_version", "pandas_version", "retrieved_on"]
        },
        "request": provider["request"],
        "cache_committed": False,
        "reproducibility": {
            "same_cache": "deterministic canonical outputs",
            "fresh_download": "not guaranteed because Yahoo history is mutable",
            "drift_detection": "per-ticker normalized SHA-256",
            "formal_candidate_requirement": "legally archivable versioned raw-data snapshot",
        },
        "period": {
            "maximum_common_start": common_start.date().isoformat(),
            "maximum_common_end": common_end.date().isoformat(),
            "effective_start": evaluation_start.date().isoformat(),
            "effective_end": evaluation_end.date().isoformat(),
            "warmup_policy": "strict full indicator readiness including 200-week SMA",
            "warmup_excluded": True,
        },
        "ready_dates": {
            ticker: value.date().isoformat()
            for ticker, value in sorted(ready_dates.items())
        },
        "splits": splits,
        "availability": availability.to_dict(orient="records"),
        "point_in_time_universe_available": False,
        "survivorship_bias_status": "present; exploratory only; not Formal Candidate",
        "jquants_api_accessed": False,
        "jquants_code_present": False,
        "premium_dependency_present": False,
        "production_hashes_verified": production_hashes,
        "fingerprint": fingerprint,
    }
    write_json(DATA_MANIFEST / "data_manifest.json", data_manifest)
    write_data_availability_report(data_manifest, availability)

    summary = {
        "schema_version": 1,
        "model_id": MODEL_ID,
        "run_id": run_id,
        "base_commit": BASE_COMMIT,
        "classification": RESULT_CLASSIFICATION,
        "formal_scenario": "basic + conservative",
        "period": data_manifest["period"],
        "splits": splits,
        "headline": headline,
        "trade_metrics": primary_trade_metrics,
        "signal_metrics": {
            "raw_signal_count": len(signals),
            "annual_signal_frequency": len(signals) / effective_years,
            **scenario_counters[("basic", "conservative")],
        },
        "longest_no_signal_period": longest_gap,
        "concentration": {
            "top_ticker_trade_share": top_ticker_share,
            "top_sector_trade_share": top_sector_share,
        },
        "path_difference": {
            "total_return_delta": optimistic_row["total_return"] - conservative_row["total_return"],
            "expectancy_delta": optimistic_row["expectancy_per_trade"] - conservative_row["expectancy_per_trade"],
            "trade_count_delta": int(optimistic_row["trade_count"] - conservative_row["trade_count"]),
        },
        "cost_assumptions": {
            name: {
                "commission_bps_per_side": cost.commission_bps_per_side,
                "slippage_bps_per_side": cost.slippage_bps_per_side,
                "round_trip_bps": cost.round_trip_bps,
            }
            for name, cost in COST_SCENARIOS.items()
        },
        "u50_u100_comparison_run": False,
    }

    write_csv(RESULTS / "u15_trades.csv", label_result(primary_trades, run_id))
    write_csv(RESULTS / "u15_yearly_metrics.csv", label_result(yearly, run_id))
    write_csv(RESULTS / "u15_monthly_signal_counts.csv", label_result(monthly, run_id))
    write_csv(RESULTS / "u15_score_bucket_metrics.csv", label_result(score_buckets, run_id))
    write_csv(RESULTS / "u15_ticker_metrics.csv", label_result(ticker_metrics, run_id))
    write_csv(RESULTS / "u15_sector_metrics.csv", label_result(sector_metrics, run_id))
    write_csv(RESULTS / "u15_cost_sensitivity.csv", label_result(cost_table, run_id))
    write_csv(RESULTS / "u15_path_sensitivity.csv", label_result(path_table, run_id))
    write_csv(RESULTS / "u15_split_metrics.csv", label_result(split_metrics, run_id))
    write_csv(RESULTS / "u15_signal_events.csv", label_result(signals, run_id))
    write_csv(RESULTS / "u15_daily_equity.csv", label_result(primary_curve, run_id))
    combined_scenarios = pd.concat(
        [
            frame.assign(scenario_key=f"{scenario}:{path}")
            for (scenario, path), frame in sorted(scenario_trades.items())
        ],
        ignore_index=True,
    )
    write_csv(
        RESULTS / "u15_scenario_trades.csv",
        label_result(combined_scenarios, run_id),
    )
    write_json(RESULTS / "u15_summary.json", summary)
    write_u15_report(
        summary,
        cost_table,
        path_table,
        score_buckets,
        ticker_metrics,
        sector_metrics,
        split_metrics,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
