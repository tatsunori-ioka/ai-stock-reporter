# J-Quants Personal Premium V2 Support Clarification

Record month: `2026-07`

Scope: J-Quants Personal Premium V2 used for private individual research.

Evidence type: summarized official written support clarification supplied by
the research owner.

## Repository privacy boundary

- This record is a non-verbatim research summary.
- The original message body, headers, signature, sender name, email address,
  contact details, ticket identifiers, and other personal data are not stored.
- No J-Quants raw data, API response, reconstructible processed data, or
  credential is included.
- The clarification applies only to Personal Premium V2. It is not evidence
  for J-Quants Pro or another provider.

## 1. Encrypted local storage during an active subscription

Status: `AVAILABLE_WHILE_SUBSCRIPTION_ACTIVE`

Data obtained through the authorized service may be stored in an encrypted
local environment while the Premium subscription remains active, provided
the purpose is private personal analysis and the acquisition date and
conditions are recorded.

After a plan downgrade, this does not permit retention of licensed data
outside the new plan. After the paid period ends or membership is withdrawn,
it does not permit retention of licensed raw data.

## 2. Aggregate-result storage and publication

Status: `AVAILABLE_WITH_PRIVATE_USE_BOUNDARY`

The following raw-free research artifacts may be retained and published
within the private-use boundary:

- CAGR;
- maximum drawdown;
- win rate;
- profit factor;
- counts, periods, and missing-value counts;
- SHA-256 values that cannot reconstruct the licensed data;
- analysis methods;
- program code; and
- backtest aggregate results that contain no raw J-Quants data.

Continuous or repeated provision or distribution of J-Quants-derived
analysis results to third parties is outside private use. This clarification
therefore does not authorize an ongoing data, signal, report, or result
distribution service. Raw or reconstructible data remains excluded.

## 3. Premium-to-Standard plan change

Status: `DELETION_REQUIRED`

When changing from Premium to Standard, all licensed data outside the new
plan's scope, together with copies and backups, must be deleted and may not
be used after the change.

## 4. Paid cancellation or membership withdrawal

Status: `DELETE_ALL_LICENSED_AND_RECONSTRUCTIBLE_DATA`

After the billed service period ends, or upon membership withdrawal, the
following must be deleted:

- licensed raw data;
- processed data from which licensed data can be reconstructed;
- copies; and
- backups.

Raw-free aggregate results, raw-free backtest results, non-reconstructive
hashes, analysis methods, and program code are outside this deletion set.

## 5. Delisted issues

Statuses:

- `AVAILABLE_BY_KNOWN_CODE`
- `POPULATION_COMPLETENESS_NOT_CONFIRMED`

When a delisted issue code is already known, data from its listed period can
be requested. This does not establish or guarantee a complete population
list of every delisted issue.

## 6. Dedicated history API coverage

The following dedicated history APIs are `NOT_AVAILABLE`:

- listing and delisting date history;
- code-change history or a permanent security identifier;
- trading-unit history;
- trading-suspension, supervision, liquidation, or equivalent status history;
  and
- comprehensive corporate-action history.

Split and reverse-split effects are `PARTIAL` through `AdjFactor`. This does
not constitute a comprehensive corporate-action event and revision history.

## Gate impact

- Formal U50/U100 possible: `false`
- Purchase recommendation: `DO_NOT_BUY_YET`
- Real-money canary authorization: `none`
- PIT-lite exploratory U50/U100 technically and usage-conditionally possible
  during an active Premium subscription for private individual research:
  `true`
- PIT-lite exploratory U50/U100 execution authorization: `none`
- Separate explicit execution approval required: `true`
- Premium recommendation: `MAINTAIN_UNTIL_EXPLORATION_COMPLETE`
- Post-exploration action:
  `CONFIRM_REQUIRED_DELETION_THEN_DECIDE_STANDARD_OR_CANCELLATION`

This clarification changes only PIT-lite exploratory readiness. It does not
promote a Formal Candidate, authorize any U50/U100 run, authorize a
real-money canary, or remove the deletion duties above.

## Non-actions in this amendment

- New provider contact or follow-up: none
- API access: none
- Raw or sample data acquisition: none
- PIT-lite or Formal U50/U100 execution: none
- Plan change, purchase, or new contract: none
- Production, Cloudflare, GitHub Actions production workflow, Google Sheets,
  Secrets, LINE, pending, and trading changes: none
