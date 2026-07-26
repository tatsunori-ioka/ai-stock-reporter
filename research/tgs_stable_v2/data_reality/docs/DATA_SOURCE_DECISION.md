# TGS Stable Ver2.0 Data Source Decision

Audit date: 2026-07-26

Base commit: `52ead3fe27c67da60d8eede4bc38fd1b4311f8ce`

Decision: `PRO_OR_ALTERNATIVE_REQUIRED`

## Decision

Do not start the Formal U50/U100 comparison.

Personal J-Quants Premium is usable for a substantial part of the research
data plane, but it is not sufficient by itself for the frozen U50/U100
selection contract. A static U50/U100 assembled without the missing data could
only be labelled survivorship-biased exploratory evidence.

No U50/U100 backtest was run or authorized by this gate.

## Frozen-contract fit

| Requirement | Finding | Decision |
| --- | --- | --- |
| Point-in-time active issue master | Five date snapshots succeeded | `AVAILABLE` |
| Later-delisted issue in historical universe | Public JPX delisted code 7829 was present in 2020, absent in latest, and retained bounded pre-delisting bars; one example does not prove complete population coverage | `PARTIAL` |
| Historical market / sector | `Mkt`, `S17`, and `S33` were returned at every probed date | `AVAILABLE` |
| Common-stock product category | `ProdCat` was returned, but its documented domestic-stock category does not by itself prove ordinary/common share class | `PARTIAL` |
| Historical market-regime mapping | Effective market codes were returned, but no frozen mapping spans First/Second Section, Mothers, JASDAQ, and Prime/Standard/Growth | `PARTIAL` |
| Raw daily OHLCV | `O/H/L/C/Vo` were returned | `AVAILABLE` |
| Traded value | `Va` was returned | `AVAILABLE` |
| Corporate-action factor | Split factors 0.5 and 0.1 and reverse-split factor 10 were observed and continuity-checked; comprehensive rights-issue/other-action coverage was not established | `PARTIAL` |
| Adjusted OHLC | `AdjO/AdjH/AdjL/AdjC/AdjVo` were returned | `AVAILABLE` |
| Dated listing interval | No direct field; first presence might be derived from dense dated snapshots from 2008 onward, but that method was not verified | `PARTIAL` |
| Dated delisting interval | No direct field; last presence might be derived, but completeness and effective-date semantics were not verified | `PARTIAL` |
| Five-year listing-history eligibility | Cannot yet be implemented reliably from the unverified presence-boundary method | `PARTIAL` |
| Ticker lineage / stable security ID | No former-code mapping, ISIN, or stable security ID | `NOT_AVAILABLE` |
| Point-in-time corporate group | No dated corporate-group mapping | `NOT_AVAILABLE` |
| Special-treatment / untradeable status | No sufficient dated eligibility/status field in the probed master | `NOT_AVAILABLE` |
| Trading unit | No trading-unit field | `NOT_AVAILABLE` |
| Dividend-inclusive return | Adjusted prices exclude dividends; Premium offers separate dividend facts but no total-return series | `PARTIAL` |
| Known-at / available-at timestamp | Master has effective `Date`, not a versioned publication timestamp | `NOT_AVAILABLE` |
| Long-term reproducible snapshot | Local hashes are possible, but persistent storage/publication needs clarification; terms impose deletion after specified cancellation paths | `SUPPORT_CONFIRMATION_REQUIRED` |
| Full frozen U15 period | Personal data begins 2008-05-07; frozen U15 effective performance begins in 2004 | `PARTIAL` |

The frozen proposal files additionally require dated listing/delisting
intervals, ticker lineage, dated corporate-group mapping, and exclusion of
special-treatment/untradeable issues. Those requirements take precedence over
a looser static-universe approximation.

## Premium and Standard

Recommendation: maintain Premium for now; do not downgrade to Standard before
the next approved gate.

Premium provides up to 20 years while Standard provides 10 years, subject to
the service-wide earliest date of 2008-05-07. Downgrading now would shorten the
already incomplete research window. This is not a recommendation to acquire a
new paid product, and this gate made no subscription change.

Do not bulk-download data merely to retain it after cancellation. The personal
terms require Data and duplicates to be deleted after the subscription's
remaining period ends and upon membership cancellation. Any pre-expiry
snapshot plan must first define:

1. the approved personal-research retention period;
2. deletion behavior at downgrade, cancellation, and expiry;
3. whether locally encrypted/versioned raw snapshots are allowed;
4. whether public aggregate metrics and response hashes are permissible; and
5. whether an approved source can supply the missing dated attributes.

The personal terms reference was last updated 2026-01-19. Its Article 1 makes
the terms prevail over inconsistent FAQ material, and Article 24 makes the
Japanese version authoritative. Ephemeral own-use processing is distinct from
persistent versioned archival; the latter remains
`SUPPORT_CONFIRMATION_REQUIRED_WITH_CANCELLATION_DELETION_DUTY`.

## U15 corporate-action-adjusted rerun

A common-period U15 rerun using J-Quants raw fields and the verified
split/reverse-split adjustment fields is technically possible from 2008-05-07
onward. Comprehensive rights-issue and other corporate-action coverage is not
established. The 200-week weekly moving-average warm-up would move the
effective analysis start later, and the run would not reproduce the full
frozen 2004–2026 U15 period.

This audit did not run that rerun. A separate approval must freeze:

- the common comparison period;
- raw versus adjusted inputs for indicators, fills, and return attribution;
- dividend treatment;
- legal local snapshot storage;
- the U15/U50/U100 common data version and hashes; and
- how the earlier frozen U15 exploratory result remains labelled.

## Pro or alternative source

J-Quants Pro is a separate professional service, not a personal Premium tier.
Its legacy corporate-action dataset documents `DelistingDate`,
`CodeBeforeChange -> Code`, and dated security-attribute changes. That dataset
is described as SFTP/Snowflake delivery, not the personal V2 REST API; its
dividend history begins 2013-02-20 and its other event history begins
2015-05-08. The 2026 Pro catalog additionally lists
`Listed Shares Flash Data` and
`Listed Shares Corporate Action Factors` with REST/SFTP/Snowflake delivery and
history from May 2008. Those newer datasets can help with listed-share-count
changes and their factors/reasons, but their published scope does not by
itself establish every required listing/delisting interval, stable identity,
corporate-group mapping, known-at timestamp for the complete point-in-time
universe and its required attributes, or archival right. Pro therefore does
not automatically solve the full historical and licensing problem. No Pro
signup, inquiry commitment, or purchase was made.

The next source gate should compare—without buying anything yet—whether Pro or
another source can jointly provide:

- dated listing and delisting intervals;
- stable security identity and code lineage;
- a frozen historical market-regime mapping and ordinary/common-share filter;
- point-in-time corporate-group mapping;
- special-treatment and tradability status;
- legally archivable, versioned raw snapshots; and
- a common history long enough for the approved comparison.

## Written support questions

Send these questions to the official J-Quants contact,
`j-quants@jpx.co.jp`, before persistent acquisition or publication:

1. May an individual Premium subscriber retain encrypted raw snapshots locally
   for reproducible personal research while the subscription is active?
2. What must be deleted after a plan downgrade, cancellation, or entitlement
   expiry, and is any research snapshot retention exception available?
3. Are one-time aggregate counts, null counts, min/max dates, derived
   continuity ratios, and SHA-256 hashes publishable in a public research
   repository?
4. Are trading unit, listing/delisting intervals, code lineage, dated
   corporate-group mapping, and special-treatment/tradability status available
   anywhere within the personal service?
5. If not, which separately licensed JPX dataset supplies them, with what
   historical start and archival rights?

Until those questions and the missing-data source are resolved:

- capability verdict remains `PRO_OR_ALTERNATIVE_REQUIRED`;
- Formal U50/U100 possible remains `false`;
- Formal U50/U100 authorization remains `none`; and
- U50/U100 execution remains stopped.
