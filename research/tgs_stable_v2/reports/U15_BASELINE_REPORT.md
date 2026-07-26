# TGS Stable Ver2.0 U15 Baseline Report

Model ID: `tgs_stable_v2_universe_lab`

Run ID: `0f6c05bff4831033`

Base commit: `43d5dd5aa6be3b0638b5af83976e61a214bd9c37`

## Gate classification

This is **survivorship-biased exploratory evidence**, not a Formal Candidate.
The current 15-name snapshot was applied backward because no point-in-time
issue master exists. No parameter was optimized, and U50/U100 were not run.

## Frozen setup

- Data: yfinance raw daily OHLCV, `auto_adjust=False`
- Period: `2004-10-29` through
  `2026-07-24`
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

- Total return: 103.45%
- CAGR: 3.32%
- Maximum drawdown: -30.91%
- Calmar ratio: 0.107
- Profit factor: 1.439
- Win rate: 47.74%
- Average win: 14.98%
- Average loss: -9.51%
- Payoff ratio: 1.575
- Expectancy per closed trade: 2.18%
- Accepted trades: 664 (664 closed,
  0 right-censored)
- Raw signal events: 2856
- Annual signal frequency: 131.41
- Longest no-signal interval: 286 market sessions /
  427 calendar days
  (`2009-01-16` to `2010-03-18`)
- Maximum consecutive losses: 16
- Average / median holding: 41.705 /
  52.500 sessions
- Market exposure: 37.22%
- Maximum simultaneous positions: 14

`total return`, CAGR, drawdown, Calmar, exposure and concurrency are from the
separate fixed equal-notional portfolio. This is a mechanical, ex-post
capacity-normalized comparison overlay, not an investable portfolio return.
Profit factor, win rate, payoff and expectancy use closed independent trades.
Right-censored trades are marked to the final Close in portfolio equity but
excluded from closed-trade statistics. Exposure and concurrency conservatively
count an exit date as occupied for that entire market session, including an
Open exit.

## Cost sensitivity

| scenario | trade_count | closed_trade_count | total_return | cagr | maximum_drawdown | profit_factor | win_rate | expectancy_per_trade |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| zero | 663 | 663 | 123.22% | 3.76% | -24.11% | 1.543 | 48.72% | 2.60% |
| basic | 664 | 664 | 103.45% | 3.32% | -30.91% | 1.439 | 47.74% | 2.18% |
| strict | 666 | 666 | 70.45% | 2.48% | -43.10% | 1.280 | 45.35% | 1.48% |

## Conservative / optimistic path sensitivity

| path_policy | trade_count | closed_trade_count | total_return | cagr | maximum_drawdown | profit_factor | win_rate | expectancy_per_trade |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| conservative | 664 | 664 | 103.45% | 3.32% | -30.91% | 1.439 | 47.74% | 2.18% |
| optimistic | 664 | 664 | 103.45% | 3.32% | -30.91% | 1.439 | 47.74% | 2.18% |

Headline total-return difference (optimistic minus conservative):
0.00%. Expectancy
difference: 0.00%.

## Score buckets

| score_bucket | signal_count | trade_count | closed_trade_count | profit_factor | win_rate | expectancy_per_trade |
| --- | --- | --- | --- | --- | --- | --- |
| 90 | 1310 | 336 | 336 | 1.467 | 46.13% | 2.41% |
| 100 | 1445 | 290 | 290 | 1.472 | 50.00% | 2.21% |
| 110 | 0 | 0 | 0 | N/A | N/A | N/A |
| 120 | 101 | 38 | 38 | 0.994 | 44.74% | -0.03% |

The 110 bucket is deliberately present and empty because 110 is unreachable
under the frozen 30/30/20/20/20 weights.

## Ticker concentration and results

| ticker | sector | signal_count | trade_count | closed_trade_count | profit_factor | win_rate | expectancy_per_trade |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5801.T | Nonferrous metals | 129 | 36 | 36 | 1.784 | 47.22% | 4.23% |
| 5802.T | Nonferrous metals | 215 | 48 | 48 | 1.619 | 52.08% | 2.99% |
| 5803.T | Nonferrous metals | 163 | 41 | 41 | 1.592 | 43.90% | 3.40% |
| 6273.T | Machinery | 260 | 56 | 56 | 0.857 | 39.29% | -0.86% |
| 6301.T | Machinery | 177 | 41 | 41 | 2.227 | 60.98% | 4.91% |
| 6367.T | Machinery | 203 | 41 | 41 | 1.535 | 56.10% | 2.34% |
| 7011.T | Machinery | 131 | 36 | 36 | 1.526 | 44.44% | 2.81% |
| 8001.T | Trading companies | 228 | 51 | 51 | 2.116 | 54.90% | 4.27% |
| 8002.T | Trading companies | 180 | 45 | 45 | 1.287 | 40.00% | 1.51% |
| 8015.T | Trading companies | 214 | 45 | 45 | 1.046 | 40.00% | 0.25% |
| 8031.T | Trading companies | 233 | 51 | 51 | 1.430 | 50.98% | 2.08% |
| 8053.T | Trading companies | 234 | 50 | 50 | 1.123 | 42.00% | 0.60% |
| 8058.T | Trading companies | 170 | 44 | 44 | 1.176 | 47.73% | 0.91% |
| 8801.T | Real estate | 179 | 39 | 39 | 1.462 | 51.28% | 2.07% |
| 8802.T | Real estate | 140 | 40 | 40 | 1.557 | 47.50% | 2.71% |

Top ticker share of accepted trades:
8.43%.

## Sector concentration and results

| sector | signal_count | trade_count | closed_trade_count | profit_factor | win_rate | expectancy_per_trade |
| --- | --- | --- | --- | --- | --- | --- |
| Machinery | 771 | 174 | 174 | 1.403 | 49.43% | 2.01% |
| Nonferrous metals | 507 | 125 | 125 | 1.658 | 48.00% | 3.48% |
| Real estate | 319 | 79 | 79 | 1.512 | 49.37% | 2.39% |
| Trading companies | 1259 | 286 | 286 | 1.338 | 46.15% | 1.66% |

Top sector share of accepted trades:
43.07%.

## Chronological split

| split | start | end | sessions | signal_count | accepted_cohort_trade_count | cross_boundary_excluded | trade_count | profit_factor | win_rate | expectancy_per_trade |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| development | 2004-10-29 | 2017-10-31 | 3190 | 1595 | 374 | 8 | 366 | 1.224 | 43.44% | 1.22% |
| validation | 2017-11-01 | 2022-03-17 | 1064 | 565 | 124 | 6 | 118 | 0.673 | 39.83% | -1.81% |
| final_holdout | 2022-03-18 | 2026-07-24 | 1064 | 696 | 166 | 0 | 166 | 2.592 | 59.04% | 6.19% |

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
PYTHONPATH=research/tgs_stable_v2/src \
python3 -m pytest research/tgs_stable_v2/tests -q

PYTHONPATH=research/tgs_stable_v2/src \
python3 research/tgs_stable_v2/run_u15.py
```

The canonical detailed outputs are in `research/tgs_stable_v2/results/`.
