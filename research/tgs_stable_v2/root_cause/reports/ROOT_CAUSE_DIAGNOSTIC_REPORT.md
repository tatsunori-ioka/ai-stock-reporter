# TGS Stable Ver2.0 PIT-lite root-cause diagnostic

- Gate: `V2-R2B_ROOT_CAUSE_DIAGNOSTIC_AND_STOP_DECISION`
- Base commit: `9dae034999aa33b3f0d059adc059d3c8dbe659c2`
- Source run: `v2-r2a-20260727-d3b8ed0-integrity1`
- Classification: `POST_HOC_ASSOCIATION_DIAGNOSTIC_ONLY`
- Diagnostic verdict: **NO_ACTIONABLE_DIAGNOSTIC_HYPOTHESIS**
- Underperformance cause: **G_CLEAR_CAUSE_NOT_IDENTIFIED**

## Scope and interpretation

This is a frozen, post-hoc association diagnostic. The final holdout had already been observed before this analysis, so it is not unused out-of-sample evidence for a future rule. The findings do not prove causality and cannot adopt a new rule, score, threshold, priority, exit, universe, or strategy.

All performance and robustness metrics require the signal, entry, and exit to be inside the same split. Signal-cohort counts remain descriptive; cross-boundary and right-censored outcomes are excluded from quality metrics.

The diagnostic used only the already licensed private cache. It made zero network calls, zero provider API calls, zero API-key reads, and zero private writes. Repository artifacts are aggregate-only.

## Integrity gates

- Private manifest: `7212e777fb613a1ff0170c54298a21979019677c466800e6edd3f0e5f1ac6d7e` (2357 exact entries)
- Normalized, membership, and ledger bundles: matched
- Frozen primary replay: U15/U50/U100 ledger, curve, and counters matched
- Production SHA: `19/19`
- Protected research SHA: `6/6`
- Position-day P&L: reconciled to every frozen primary equity curve
- Deterministic same-private-cache rerun: PASS

## Score components

Score monotonicity: **NOT_ESTABLISHED**.
Score 120 diagnosis: **INSUFFICIENT_SAMPLE_FOR_ROBUST_SCORE120_HYPOTHESIS**.

| Universe | Score 90 expectancy | Score 100 expectancy | Score 120 expectancy | Strict monotonicity |
|---|---:|---:|---:|---|
| U15_ADJUSTED_STATIC | 2.685% | 2.243% | -0.857% | no |
| U50_PIT_LITE | 0.378% | 1.671% | -0.750% | no |
| U100_PIT_LITE | 1.242% | 1.254% | 0.419% | no |

The combination table records the exact five-bit component masks, including volume, MACD-GC, and 200-week-MA membership, but no component is promoted into a changed rule.

Score 120 is the all-five-condition mask, so it cannot isolate one component effect. Its validation and holdout samples remain below the pre-registered 30-closed-trades-per-arm floor. The observed Score 120 shortfall is descriptive; its cause is not identified. Volume/no-volume, MACD-GC/no-GC, and 200-week-MA/no-MA rows remain association-only and are confounded by the other mask components.

## Robust hypothesis gate

| Hypothesis | Status | Fully evaluable | Robust conditions passed |
|---|---|---:|---:|
| A_ADDED_SIGNAL_QUALITY | EVALUATED_NOT_ACTIONABLE | true | false |
| B_CAPACITY_PRIORITY | EVALUATED_NOT_ACTIONABLE | true | false |
| C_HIGH_EXPOSURE | INSUFFICIENT_SAMPLE | false | false |
| D_EXIT_ATTRIBUTION | EVALUATED_NOT_ACTIONABLE | true | false |
| E_SCORE_MONOTONICITY | INSUFFICIENT_SAMPLE | false | false |

A hypothesis is actionable only when validation and final holdout agree in both U50 and U100, both arms have at least 30 closed trades per split, ticker and sector leave-one-out directions hold, concentration limits pass, and the 10,000-replicate signal-month cluster bootstrap is direction-stable.

| Hypothesis | Universe | Split | Left n | Right n | Mean difference | 95% cluster CI | Failure reasons |
|---|---|---|---:|---:|---:|---:|---|
| A_ADDED_SIGNAL_QUALITY | U50_PIT_LITE | validation | 978 | 174 | -0.0856 | [-0.1257, -0.0322] | CONCENTRATION_LIMIT_FAILED |
| A_ADDED_SIGNAL_QUALITY | U50_PIT_LITE | final_holdout | 1142 | 178 | -0.0259 | [-0.0714, 0.0163] | BOOTSTRAP_UNSTABLE |
| A_ADDED_SIGNAL_QUALITY | U100_PIT_LITE | validation | 2053 | 263 | -0.0799 | [-0.1112, -0.0432] | CONCENTRATION_LIMIT_FAILED |
| A_ADDED_SIGNAL_QUALITY | U100_PIT_LITE | final_holdout | 2142 | 299 | -0.0386 | [-0.0712, -0.0034] | none |
| B_CAPACITY_PRIORITY | U50_PIT_LITE | validation | 678 | 50 | -0.0161 | [-0.0613, 0.0224] | DIRECTION_MISMATCH, BOOTSTRAP_UNSTABLE, TICKER_LOO_UNSTABLE, SECTOR_LOO_UNSTABLE |
| B_CAPACITY_PRIORITY | U50_PIT_LITE | final_holdout | 727 | 69 | -0.0074 | [-0.0480, 0.0293] | DIRECTION_MISMATCH, BOOTSTRAP_UNSTABLE, TICKER_LOO_UNSTABLE, SECTOR_LOO_UNSTABLE |
| B_CAPACITY_PRIORITY | U100_PIT_LITE | validation | 1765 | 89 | -0.0105 | [-0.0446, 0.0215] | DIRECTION_MISMATCH, BOOTSTRAP_UNSTABLE, TICKER_LOO_UNSTABLE, SECTOR_LOO_UNSTABLE |
| B_CAPACITY_PRIORITY | U100_PIT_LITE | final_holdout | 1850 | 102 | -0.0055 | [-0.0419, 0.0301] | DIRECTION_MISMATCH, BOOTSTRAP_UNSTABLE, TICKER_LOO_UNSTABLE, SECTOR_LOO_UNSTABLE |
| C_HIGH_EXPOSURE | U50_PIT_LITE | validation | 81 | 34 | -0.0173 | [-0.0762, 0.0299] | INSUFFICIENT_SAMPLE_OR_LOO, BOOTSTRAP_UNSTABLE, SECTOR_LOO_UNSTABLE |
| C_HIGH_EXPOSURE | U50_PIT_LITE | final_holdout | 97 | 61 | -0.0285 | [-0.0855, 0.0222] | BOOTSTRAP_UNSTABLE |
| C_HIGH_EXPOSURE | U100_PIT_LITE | validation | 93 | 32 | 0.0044 | [-0.0608, 0.0634] | INSUFFICIENT_SAMPLE_OR_LOO, DIRECTION_MISMATCH, BOOTSTRAP_UNSTABLE, TICKER_LOO_UNSTABLE, SECTOR_LOO_UNSTABLE |
| C_HIGH_EXPOSURE | U100_PIT_LITE | final_holdout | 101 | 53 | -0.0252 | [-0.0921, 0.0510] | BOOTSTRAP_UNSTABLE |
| D_EXIT_ATTRIBUTION | U50_PIT_LITE | validation | 978 | 174 | 0.2812 | [0.1585, 0.3715] | CONCENTRATION_LIMIT_FAILED |
| D_EXIT_ATTRIBUTION | U50_PIT_LITE | final_holdout | 1142 | 178 | 0.0676 | [-0.0694, 0.2071] | BOOTSTRAP_UNSTABLE |
| D_EXIT_ATTRIBUTION | U100_PIT_LITE | validation | 2053 | 263 | 0.3094 | [0.2038, 0.4004] | CONCENTRATION_LIMIT_FAILED |
| D_EXIT_ATTRIBUTION | U100_PIT_LITE | final_holdout | 2142 | 299 | 0.1132 | [0.0033, 0.2138] | none |
| E_SCORE_MONOTONICITY | U50_PIT_LITE | validation | 9 | 106 | -0.0677 | [n/a, n/a] | INSUFFICIENT_SAMPLE_OR_LOO, BOOTSTRAP_UNSTABLE, TICKER_LOO_UNSTABLE, SECTOR_LOO_UNSTABLE |
| E_SCORE_MONOTONICITY | U50_PIT_LITE | final_holdout | 12 | 146 | 0.0240 | [n/a, n/a] | INSUFFICIENT_SAMPLE_OR_LOO, DIRECTION_MISMATCH, BOOTSTRAP_UNSTABLE, TICKER_LOO_UNSTABLE, SECTOR_LOO_UNSTABLE |
| E_SCORE_MONOTONICITY | U100_PIT_LITE | validation | 14 | 111 | -0.0290 | [n/a, n/a] | INSUFFICIENT_SAMPLE_OR_LOO, BOOTSTRAP_UNSTABLE, TICKER_LOO_UNSTABLE, SECTOR_LOO_UNSTABLE |
| E_SCORE_MONOTONICITY | U100_PIT_LITE | final_holdout | 20 | 134 | 0.0205 | [n/a, n/a] | INSUFFICIENT_SAMPLE_OR_LOO, DIRECTION_MISMATCH, BOOTSTRAP_UNSTABLE, TICKER_LOO_UNSTABLE, SECTOR_LOO_UNSTABLE |

A compares added-code versus U15-static-code frozen one-shot quality. B compares capacity-rejected candidates with accepted candidates on the same capacity-binding sessions. C compares high versus lower cash-utilization accepted trades and requires drawdown support. D measures negative-exit burden only and tests no alternative exit. E compares Score 120 with pooled Scores 90/100.

## Validation / holdout decomposition

| Universe | Split | Signals / 100 sessions | Closed | PF | Expectancy | Cash utilization | Exposure | Max DD | Capacity rejection share | Top ticker share | Top sector share | Stop-family share | Max-holding share |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| U15_ADJUSTED_STATIC | validation | 72.92 | 76 | 2.236 | 4.32% | 64.14% | 100.00% | -12.82% | 7.53% | 9.21% | 48.68% | 32.89% | 56.58% |
| U15_ADJUSTED_STATIC | final_holdout | 59.97 | 92 | 2.562 | 6.82% | 61.70% | 94.35% | -16.09% | 4.17% | 11.96% | 34.78% | 36.96% | 35.87% |
| U50_PIT_LITE | validation | 220.43 | 115 | 1.464 | 2.07% | 93.04% | 100.00% | -19.68% | 86.34% | 5.22% | 16.52% | 37.39% | 53.91% |
| U50_PIT_LITE | final_holdout | 226.41 | 158 | 1.209 | 1.27% | 90.27% | 100.00% | -27.56% | 81.64% | 4.43% | 17.09% | 52.53% | 31.65% |
| U100_PIT_LITE | validation | 438.70 | 125 | 1.381 | 1.88% | 95.88% | 100.00% | -21.01% | 93.76% | 3.20% | 19.20% | 44.00% | 48.00% |
| U100_PIT_LITE | final_holdout | 425.91 | 154 | 1.388 | 2.20% | 94.51% | 100.00% | -29.79% | 92.17% | 3.25% | 18.83% | 47.40% | 34.42% |

Expansion changed frequency, diversification, exposure, and capacity pressure, but no A–E explanation satisfied every robustness condition. The cause classification therefore remains G and is not a causal finding.

## Exit, capacity, and drawdown attribution

- Exit attribution: `EVALUATED_NOT_ACTIONABLE`; no alternative exit was tested.
- Capacity attribution: `EVALUATED_NOT_ACTIONABLE`; the frozen priority was not changed.
- Drawdowns: the top five non-overlapping watermark episodes per universe are recorded with anonymous ticker/sector concentration, score and exit-reason gross-loss shares, capacity pressure, signal frequency, and internal regime proxies.
- Gross-negative contribution and net position P&L are labeled separately. Net position-day P&L reconciles to the peak-to-trough equity change.
- MFE/MAE use the pre-registered conservative executable OHLC path and entry-cash denominator; prices after the frozen trigger are excluded.
- Capacity counts use signal cohorts, while quality comparisons use split-contained one-shot outcomes.
- Anonymous drawdown gross-loss shares are descriptive attribution, not causal attribution.

## U15 / U50 / U100 decomposition

The regime table separates signal quality, accepted-trade quality, exposure, cash utilization, capacity rejection, ticker/sector diversification, stop frequency, max-holding frequency, and validation/holdout behavior. The classification is constrained by the pre-registered A–G policy and is not a causal claim.

## Decision and authorizations

- Diagnostic verdict: **NO_ACTIONABLE_DIAGNOSTIC_HYPOTHESIS**
- Actionable hypotheses: `none`
- Recommended final action: **END_TGS_STABLE_V2_RESEARCH**
- Formal Candidate: HOLD
- Formal U50/U100: NOT_AUTHORIZED
- Real-money canary: none
- New rule / optimization: not executed and not authorized
- Private cleanup: NOT_EXECUTED
- Premium change or cancellation: not authorized by this gate
- Ver1.0 production: unchanged

- Licensed private cache: `RECOMMEND_SEPARATE_APPROVAL_FOR_LICENSED_DATA_CLEANUP`
- Premium plan: `PROCEED_TO_STANDARD_OR_CANCELLATION_DECISION_AFTER_CLEANUP_CONFIRMATION`
- Ver1.0 Cloud monitoring: `KEEP_OBSERVATION_ONLY_IF_MONITORING_VALUE_REMAINS; OTHERWISE_STOP`

The recommendation is to end TGS Stable Ver2.0 research. Licensed-data cleanup requires separate approval. Only after cleanup confirmation should Premium-to-Standard or cancellation be decided. Keep Ver1.0 Cloud monitoring observation-only only if it retains monitoring value; otherwise stop it.

PIT-lite limitations remain: sector is an annual snapshot; stable security lineage, unified known-at timestamps, comprehensive corporate actions, complete delisted-population coverage, and full special-treatment history are unavailable. Intraday ordering is not observed, and frozen-end outcomes can be right-censored.

No new formal signal may be connected to real-money trading. Any cleanup, plan change, follow-up research, production change, or merge requires its own explicit decision.
