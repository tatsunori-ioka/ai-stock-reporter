# PIT-lite U15/U50/U100 comparison report

- Gate: `V2-R2A_PIT_LITE_UNIVERSE_COMPARISON`
- Base: `d3b8ed0ec09d6d7fc70aeca5144f8bb6962c4073`
- Run: `v2-r2a-20260727-d3b8ed0-integrity1`
- Classification: `PIT_LITE_EXPLORATORY_ONLY_NOT_FORMAL_CANDIDATE`
- Effective common period: 2014-04-01 to 2026-07-24
- Primary: basic cost, conservative same-day path, JPY 10 million fractional ten-slot proxy.

This is Personal Premium PIT-lite exploratory evidence. It is not Formal U50/U100 and does not authorize a Formal Candidate, production change, purchase, or real-money canary.

## Primary aggregate metrics

| Universe | CAGR | Max DD | PF | Expectancy | Accepted entries |
|---|---:|---:|---:|---:|---:|
| U15_ADJUSTED_STATIC | 6.49% | -37.55% | 1.493 | 2.28% | 402 |
| U15_RAW_COMMON_PERIOD | 9.38% | -34.61% | 1.801 | 3.92% | 382 |
| U50_PIT_LITE | 4.51% | -44.67% | 1.198 | 1.01% | 655 |
| U100_PIT_LITE | 6.15% | -48.54% | 1.225 | 1.17% | 712 |

## Frequency

- U15_ADJUSTED_STATIC: 145.95 raw events/year, 32.65 accepted entries/year; longest no-signal period 56 sessions / 83 calendar days.
- U15_RAW_COMMON_PERIOD: 138.97 raw events/year, 31.03 accepted entries/year; longest no-signal period 56 sessions / 83 calendar days.
- U50_PIT_LITE: 473.10 raw events/year, 53.20 accepted entries/year; longest no-signal period 29 sessions / 45 calendar days.
- U100_PIT_LITE: 959.69 raw events/year, 57.83 accepted entries/year; longest no-signal period 25 sessions / 38 calendar days.

## Validation and final holdout

| Universe | Split | PF | Expectancy | Trades | Cross-boundary excluded |
|---|---|---:|---:|---:|---:|
| U15_ADJUSTED_STATIC | validation | 2.236 | 4.32% | 76 | 10 |
| U15_ADJUSTED_STATIC | final_holdout | 2.562 | 6.82% | 92 | 0 |
| U15_RAW_COMMON_PERIOD | validation | 2.236 | 4.32% | 76 | 10 |
| U15_RAW_COMMON_PERIOD | final_holdout | 1.937 | 5.40% | 69 | 0 |
| U50_PIT_LITE | validation | 1.464 | 2.07% | 115 | 10 |
| U50_PIT_LITE | final_holdout | 1.209 | 1.27% | 168 | 0 |
| U100_PIT_LITE | validation | 1.381 | 1.88% | 125 | 10 |
| U100_PIT_LITE | final_holdout | 1.388 | 2.20% | 164 | 0 |

## Concentration

| Universe | Top ticker trade share | Top sector trade share | Entries |
|---|---:|---:|---:|
| U15_ADJUSTED_STATIC | 7.71% | 43.03% | 402 |
| U15_RAW_COMMON_PERIOD | 8.12% | 42.67% | 382 |
| U50_PIT_LITE | 3.21% | 17.25% | 655 |
| U100_PIT_LITE | 2.39% | 17.84% | 712 |

## Cost sensitivity

| Universe | Cost | CAGR | Max DD | PF |
|---|---|---:|---:|---:|
| U15_ADJUSTED_STATIC | zero | 7.90% | -32.96% | 1.603 |
| U15_ADJUSTED_STATIC | basic | 6.49% | -37.55% | 1.493 |
| U15_ADJUSTED_STATIC | strict | 3.86% | -45.52% | 1.301 |
| U15_RAW_COMMON_PERIOD | zero | 10.85% | -32.07% | 1.924 |
| U15_RAW_COMMON_PERIOD | basic | 9.38% | -34.61% | 1.801 |
| U15_RAW_COMMON_PERIOD | strict | 6.72% | -38.07% | 1.589 |
| U50_PIT_LITE | zero | 5.28% | -41.22% | 1.233 |
| U50_PIT_LITE | basic | 4.51% | -44.67% | 1.198 |
| U50_PIT_LITE | strict | 0.82% | -55.47% | 1.057 |
| U100_PIT_LITE | zero | 7.89% | -41.96% | 1.291 |
| U100_PIT_LITE | basic | 6.15% | -48.54% | 1.225 |
| U100_PIT_LITE | strict | 0.56% | -56.82% | 1.034 |

## Path, terminal and portfolio diagnostics

| Universe | Primary CAGR | Optimistic CAGR | Last-close CAGR | Independent PF | Equal-notional CAGR |
|---|---:|---:|---:|---:|---:|
| U15_ADJUSTED_STATIC | 6.49% | 6.49% | 6.49% | 1.460 | 4.08% |
| U15_RAW_COMMON_PERIOD | 9.38% | 9.38% | 9.38% | 1.765 | 6.04% |
| U50_PIT_LITE | 4.51% | 4.51% | 4.51% | 1.138 | 1.90% |
| U100_PIT_LITE | 6.15% | 6.15% | 6.15% | 1.171 | 2.35% |

## Raw / adjusted U15 diagnostic

- Adjusted U15 CAGR / DD / PF: 6.49% / -37.55% / 1.493
- Raw U15 CAGR / DD / PF: 9.38% / -34.61% / 1.801
- Raw-minus-adjusted CAGR delta: 2.89%

## Annual Universe counts

Selection years are 2014–2026 (13 annual selections).

| Universe | Selected count range | Shortfall years |
|---|---:|---:|
| U50_PIT_LITE | 50–50 | 0 |
| U100_PIT_LITE | 100–100 | 0 |

## API and licensed-data audit

- New-run HTTP attempts: 1028
- Prior aborted-run attempts: 156
- Gate attempts used: 1184 / 3000
- Expected attempts: 1310; planned fallback worst case: 2373
- FileVault active at comparison: true
- Raw licensed data committed: false
- Private cleanup: NOT_EXECUTED


## Exploratory economic gate

- Overall: **MIXED**
- U50_PIT_LITE: **MIXED** (6/11 criteria; drawdown-vs-U15 is fail-closed pending a numeric threshold)
- U100_PIT_LITE: **MIXED** (6/11 criteria; drawdown-vs-U15 is fail-closed pending a numeric threshold)

| Universe | Criterion | Result |
|---|---|---|
| U50_PIT_LITE | `cagr_at_least_10pct` | FAIL |
| U50_PIT_LITE | `maximum_drawdown_at_least_minus_30pct` | FAIL |
| U50_PIT_LITE | `profit_factor_at_least_1_3` | FAIL |
| U50_PIT_LITE | `validation_expectancy_positive` | PASS |
| U50_PIT_LITE | `validation_profit_factor_above_1` | PASS |
| U50_PIT_LITE | `holdout_expectancy_positive` | PASS |
| U50_PIT_LITE | `holdout_profit_factor_above_1` | PASS |
| U50_PIT_LITE | `cagr_advantage_over_u15_at_least_5pp` | FAIL |
| U50_PIT_LITE | `maximum_drawdown_vs_u15` | FAIL |
| U50_PIT_LITE | `top_ticker_trade_share_at_most_15pct` | PASS |
| U50_PIT_LITE | `top_sector_trade_share_at_most_35pct` | PASS |
| U100_PIT_LITE | `cagr_at_least_10pct` | FAIL |
| U100_PIT_LITE | `maximum_drawdown_at_least_minus_30pct` | FAIL |
| U100_PIT_LITE | `profit_factor_at_least_1_3` | FAIL |
| U100_PIT_LITE | `validation_expectancy_positive` | PASS |
| U100_PIT_LITE | `validation_profit_factor_above_1` | PASS |
| U100_PIT_LITE | `holdout_expectancy_positive` | PASS |
| U100_PIT_LITE | `holdout_profit_factor_above_1` | PASS |
| U100_PIT_LITE | `cagr_advantage_over_u15_at_least_5pp` | FAIL |
| U100_PIT_LITE | `maximum_drawdown_vs_u15` | FAIL |
| U100_PIT_LITE | `top_ticker_trade_share_at_most_15pct` | PASS |
| U100_PIT_LITE | `top_sector_trade_share_at_most_35pct` | PASS |

An `EXPLORATORY_PROMISE_PASS` here would still have no promotion effect. The undefined “drawdown not significantly worse than U15” condition was frozen before results as `MANUAL_THRESHOLD_REQUIRED_FAIL_CLOSED`.

## Data and method limitations

- The complete delisted-issue population is not guaranteed.
- U15 adjusted/static is survivorship-biased: the current 15 names are applied backward through history.
- Active-issue, market and S33 sector values are effective-date snapshots; record-level known-at timestamps are unavailable.
- Five-year history uses first observed bar, not listing date.
- Corporate-group and complete special-treatment histories are unavailable and no substitute was inferred.
- Historical trading units are unavailable; the fractional-notional capital proxy does not prove Japanese round-lot executability.
- Codes are not stitched; comprehensive corporate-action coverage is not established; adjusted bars exclude dividends.
- U15 raw is diagnostic only. Premature data ends use a 20% haircut in the primary and last-close in sensitivity.
- Repository artifacts contain aggregates and non-reconstructible hashes only. Raw bars, annual members and exact ledgers remain in the FileVault-protected private root.

## Authorization state

- Formal U50/U100: not authorized
- Formal Candidate: HOLD
- Real-money canary: none
- Premium recommendation: maintain through approved exploration; cleanup remains NOT_EXECUTED

## Canonical aggregate artifacts

- [`metrics_summary.json`](../results/metrics_summary.json)
- [`split_metrics.csv`](../results/split_metrics.csv)
- [`yearly_metrics.csv`](../results/yearly_metrics.csv)
- [`score_bucket_metrics.csv`](../results/score_bucket_metrics.csv)
- [`cost_sensitivity.csv`](../results/cost_sensitivity.csv)
- [`concentration_metrics.csv`](../results/concentration_metrics.csv)
- [`universe_annual_counts.csv`](../results/universe_annual_counts.csv)
- [`data_fingerprints.json`](../results/data_fingerprints.json)
- [`request_audit_summary.json`](../results/request_audit_summary.json)
