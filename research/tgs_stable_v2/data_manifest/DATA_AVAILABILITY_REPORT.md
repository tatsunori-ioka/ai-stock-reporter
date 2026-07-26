# TGS Stable Ver2.0 Data Availability Report

## Decision

U15 data is available for a long exploratory baseline, but the repository
cannot construct a point-in-time universe. The result is therefore
**survivorship-biased exploratory evidence** and is not a Formal Candidate.

## Acquisition

- Provider: Yahoo Finance via yfinance
- yfinance: `1.5.2`
- pandas: `3.0.5`
- Request: `1990-01-01` through
  `2026-07-27` (end-exclusive)
- `auto_adjust=False`; indicators and fills use raw OHLCV.
- Raw cache committed: no
- Raw normalized data hash recorded per ticker: yes
- Same-cache rerun: deterministic
- Fresh-download caveat: Yahoo history is mutable; hashes detect drift but the
  ignored cache cannot reconstruct a prior snapshot.

## Period and warm-up

- Maximum common raw window: `2001-01-04`
  through `2026-07-24`
- Effective test window after common indicator warm-up:
  `2004-10-29` through
  `2026-07-24`
- Warm-up rule: all required inputs ready, dominated by the 200-week SMA.
- Warm-up rows are excluded from performance.

## Ticker coverage

| ticker | first_date | last_date | rows | missing_vs_union_sessions | duplicate_dates | nonpositive_ohlc_rows_removed | nonpositive_volume_rows_removed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6273.T | 2001-01-04 | 2026-07-24 | 6248 | 5 | 0 | 0 | 120 |
| 6301.T | 2000-01-04 | 2026-07-24 | 6494 | 3 | 0 | 0 | 133 |
| 6367.T | 2000-01-04 | 2026-07-24 | 6494 | 3 | 0 | 0 | 133 |
| 7011.T | 2000-01-04 | 2026-07-24 | 6494 | 3 | 0 | 0 | 133 |
| 5801.T | 2000-01-04 | 2026-07-24 | 6496 | 1 | 0 | 0 | 131 |
| 5802.T | 2000-01-04 | 2026-07-24 | 6492 | 5 | 0 | 0 | 135 |
| 5803.T | 2000-01-04 | 2026-07-24 | 6494 | 3 | 0 | 0 | 133 |
| 8801.T | 2000-01-04 | 2026-07-24 | 6494 | 3 | 0 | 0 | 133 |
| 8802.T | 2000-01-04 | 2026-07-24 | 6494 | 3 | 0 | 0 | 133 |
| 8001.T | 2000-01-04 | 2026-07-24 | 6494 | 3 | 0 | 0 | 133 |
| 8002.T | 2000-01-04 | 2026-07-24 | 6494 | 3 | 0 | 0 | 133 |
| 8015.T | 2000-01-04 | 2026-07-24 | 6492 | 5 | 0 | 0 | 135 |
| 8031.T | 2000-01-04 | 2026-07-24 | 6497 | 0 | 0 | 0 | 130 |
| 8053.T | 2000-01-04 | 2026-07-24 | 6494 | 3 | 0 | 0 | 133 |
| 8058.T | 2000-01-04 | 2026-07-24 | 6494 | 3 | 0 | 0 | 133 |

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
