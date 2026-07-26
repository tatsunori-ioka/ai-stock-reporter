# TGS Stable Ver2.0 Universe Lab — Frozen Research Contract

Model ID: `tgs_stable_v2_universe_lab`

Base commit: `43d5dd5aa6be3b0638b5af83976e61a214bd9c37`

## Gate status

This contract freezes TGS Stable Ver1.0 before any U15 numerical result is
examined. U50 and U100 are proposals only; their comparison backtests are not
authorized in this gate.

The current Cloud production path is score-check-only. This research neither
imports nor writes production ledgers, and it cannot dispatch workflows,
deploy Cloudflare, send LINE notifications, connect to Sheets, or place an
order.

## Frozen U15 and score

The authoritative U15 order is the list in
`stable_cloud_score_check.py:45-61`. The score is:

```text
30 * weekly_above_200ma
+ 30 * weekly_macd_gc
+ 20 * weekly_macd_uptrend
+ 20 * daily_rsi_40_65
+ 20 * daily_volume_1_5x
```

The threshold is inclusive at 90 and the maximum is 120. Missing boolean
conditions are false. Score 110 is not reachable with these weights, so the
110 report bucket must exist and remain empty.

## Indicator parity

- Daily RSI is the Ver1.0 14-session EWM implementation.
- Daily volume is compared with its current-session-inclusive 30-session SMA.
- Weekly bars use `W-FRI`, with first/max/min/last/sum OHLCV aggregation.
- Weekly trend uses a raw-Close 200-week SMA and MACD 12/26/9.
- Friday-labelled weekly data forward-fills to later daily rows. A partial
  Monday–Thursday week has a future Friday label and cannot flow backward.
- Research performance starts only when every required indicator, including
  the 200-week SMA, is ready. The warm-up is excluded.

## Data contract

The U15 baseline uses the same mode as Ver1.0: Yahoo Finance through
`yfinance`, one-day bars, `auto_adjust=False`, and raw
Open/High/Low/Close/Volume. `Adj Close` is retained only for audit and is not
used by the score or fills.

Rows with missing required OHLCV, nonpositive OHLC, or `Volume <= 0` are
non-trading/provider-placeholder rows. They are excluded before indicators,
market-session construction, fills, and holding-session counts. Their removed
counts are retained in the data manifest.

The repository has no point-in-time listing, delisting, sector, market-cap, or
ticker-lineage table. U15 is a current surviving snapshot applied backward.
Every result is therefore labelled **survivorship-biased exploratory
evidence**, never a Formal Candidate.

## Execution contract

This is the V2 research execution overlay required by the gate, not a
byte-for-byte replay of the dormant Ver1 paper ledger. It freezes Ver1's
direction, next-session entry, duplicate guard, stop/take percentages and
60-session hold. It deliberately adds the mandated gap, cost, missing-bar and
path-sensitivity rules. The dormant Ver1 implementation instead queues a
missing entry bar, fills gap exits at the threshold, and has a separate
3-million-yen / 500,000-yen / six-position ledger capacity.

- Information available through signal-date Close only.
- Entry at the next market session Open; signal-day Close fills are forbidden.
- One long position per ticker; overlapping signals while held are ignored.
- Stop is 10% below actual entry fill; take profit is 30% above it.
- A stop gap or take-profit gap fills from raw Open, then adverse slippage.
- If both levels occur intraday, the formal path is conservative
  (stop-first); optimistic take-first is sensitivity only.
- The entry session is holding session 1. The 60th observed ticker session
  exits at Close if no earlier exit occurs.
- A missing next-market-session bar is unfilled, not delayed.
- A right-censored trade is marked to its last available Close, clearly
  flagged, and excluded from closed-trade statistics.

## Ex-ante cost scenarios

These values were fixed before the U15 run and were not fitted:

| Scenario | Commission/side | Slippage/side | Round trip |
| --- | ---: | ---: | ---: |
| zero | 0 bp | 0 bp | 0 bp |
| basic | 10 bp | 10 bp | 40 bp |
| strict | 20 bp | 30 bp | 100 bp |

The formal headline uses `basic + conservative`.

## Portfolio and time split

Independent one-signal results come first. The separate simple portfolio gives
one fixed notional unit to every accepted trade. Initial capital is the
observed maximum simultaneous unit positions, so there is no leverage,
selection, reinvestment, or capital optimization. This ex-post capacity
normalization is a mechanical comparison overlay, not an investable portfolio
construction. Exposure and concurrency conservatively count the exit date as
occupied for the full market session, including an Open exit.

After the common warm-up, sessions are split chronologically 60% development,
20% validation, and 20% final holdout. Rules are frozen and the final holdout
is not used for optimization. Split-level trade metrics include only a signal
cohort whose exit is also inside the same split. Cross-boundary trades are
counted and excluded from split statistics so validation cannot consume final
holdout prices. Split outputs are closed independent-trade cohort statistics,
not split-level portfolio return or drawdown. Annual portfolio returns use the
prior calendar close as their opening anchor, while annual trade statistics
use exit year and separately report signal-year cohort counts.

## U50/U100 gate

The proposal files were fixed before viewing U15 results. Selection is
liquidity-ranked and return-blind, with listing-history, price, data-quality,
sector and corporate-group constraints. A formal comparison requires dated
point-in-time reference data. A current static fallback can only be described
as survivorship-biased exploration. Both proposal file SHA-256 values are
frozen in the machine-readable contract and included in every run fingerprint.

The machine-readable contract, including protected-file SHA-256 values, is
`contracts/ver1_baseline_contract.json`.
