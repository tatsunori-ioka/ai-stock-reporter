# PIT-lite method

## Classification

`PIT_LITE_EXPLORATORY_ONLY_NOT_FORMAL_CANDIDATE`

The dated J-Quants master supplies effective-date active issues, market and
sector attributes. It does not supply a permanent security identifier,
complete listing/delisting history, corporate-group history, complete
special-treatment history, or a versioned known-at timestamp. The experiment
therefore cannot be described as Formal U50/U100.

The complete delisted-issue population is not guaranteed. Historical trading
units are unavailable, and the current U15 names applied backward through
history are an explicitly survivorship-biased static comparator.

## Annual selection

For each year from 2014 through 2026, the selection becomes effective on the
first JPX session in April and uses information no later than the preceding JPX
session close. Membership remains fixed until the next annual selection.

The frozen historical market map includes TSE First, TSE Second, JASDAQ
Standard, Prime and Standard. Domestic equity is the documented product
category code `011` (`内国株券`) from the official
[`/equities/master` product-category table](https://jpx-jquants.com/ja/spec/eq-master/product-category);
the sector cap uses the effective-date S33 value.
Eligible rows require that product category, 247 or more
complete positive raw OHLCV observations in the preceding 252 JPX sessions,
five calendar years since the first observed bar, raw cutoff close of at least
JPY 300, and a prior-60-session median provider `Va` at the applicable
threshold. Ranking is `Va` descending then code ascending. Sector caps are
greedy and shortages are reported without relaxation.

Provider security codes are accepted only as exactly five uppercase ASCII
letters or digits, covering the official alphanumeric equity-code regime while
preventing path traversal.

Corporate groups are unavailable and no substitute is used. The first
observed bar is explicitly a listing-history proxy. Codes are never stitched.

## Signals and fills

The frozen TGS score is calculated on full-history adjusted bars, without
resetting indicators at annual membership changes. A signal is eligible only
when the security belongs to that universe on the signal session. Entry is at
the next official JPX session Open; a missing security bar means no delayed
fill. Positions remain open after later universe removal.

Stop loss is -10%, take profit is +30%, and maximum holding is 60 observed
ticker sessions. Gaps fill at Open. The primary same-day ambiguity is
stop-first; take-first is a sensitivity. Entry-day exits are permitted.

At a portfolio session Open, known Open-gap exits of existing positions are
processed first. Candidates are then ranked by score, signal-date 60-session
median `Va`, and code; Open entries use only then-available cash and slots.
Intraday/Close exits occur after entry allocation and cannot retroactively fund
those Open entries.

## Portfolios and splits

The diagnostics are independent trades, PR #7-compatible fixed
equal-notional/capacity normalization, and a JPY 10 million fractional-share
cash proxy with ten slots and at most 10% of Open equity per position. The
primary is basic cost, conservative path, ten-slot proxy.

All universes share one common valid-session window and fixed chronological
60/20/20 development, validation and final-holdout boundaries. No optimization
is performed. Split trade metrics use signal-date cohorts and exclude trades
whose lifecycle crosses a split boundary.

## Economic gate

The numeric criteria are frozen in the contract. The phrase “drawdown not
significantly worse than U15” lacked a numeric tolerance at authorization, so
that criterion is fail-closed and reported as
`MANUAL_THRESHOLD_REQUIRED_FAIL_CLOSED`. A PIT-lite verdict cannot authorize a
Formal Candidate, real-money canary, purchase, or production change.
