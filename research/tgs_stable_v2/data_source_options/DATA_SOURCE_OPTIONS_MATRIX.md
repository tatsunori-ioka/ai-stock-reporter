# V2-R1C Data Source Options Matrix

Audit date: 2026-07-27

Base commit: `4f59764cfef49f7a9c0781469d30912e7f7826b0`

Gate: `V2-R1C_DATA_SOURCE_OPTIONS`

Evidence boundary: the comparative review uses official, publicly accessible
provider and exchange materials. The J-Quants Personal Premium V2 cells also
use a written support clarification received in 2026-07. Only the
non-verbatim research summary in
`JQUANTS_SUPPORT_CLARIFICATION_2026_07.md` is retained; the original message,
headers, names, addresses, and other personal data are not stored. This
amendment performed no new provider contact, API access, raw-data acquisition,
purchase, contract, plan change, or U50/U100 execution.

## Gate result

- Confirmed option meeting the most requirements: `none`
- Highest documented Japan-specific field coverage:
  `QUICK` (conditional and limited by the published 2014/2015 history)
- Strongest enterprise point-in-time framing:
  `BLOOMBERG` (conditional; not a Japan-field pass)
- Strongest explicitly documented domestic point-in-time design:
  `TOYO_TREND3EPOT` (conditional)
- Lowest publicly priced access:
  `DATA_GET2`, but it is not a Formal U50/U100 source and its published
  individual-use terms are incompatible with the required derived research
  workflow.
- Lowest publicly priced official-exchange file route:
  `JPX_DATACUBE`, but it does not supply the missing point-in-time
  security-state contract by itself.
- Lowest publicly priced corporate bundle worth a written scope inquiry:
  `JPX_DIRECT`, with a public current-feed subtotal from
  JPY 284,000/month excluding tax for a non-financial single entity. The
  required historical backfill, point-in-time semantics, and research
  rights are not established by that subtotal.
- Individual-contract candidates:
  J-Quants Personal, J-Quants DataCube, and DATA-GET2. None is sufficient
  for Formal U50/U100.
- Explicit legal-entity-only candidate:
  J-Quants Pro.
- Formal U50/U100 possible after the support clarification: `false`
- Purchase recommendation now: `DO_NOT_BUY_YET`
- Formal U50/U100 execution authorization: `none`
- PIT-lite exploratory U50/U100 technically and usage-conditionally possible
  while Premium remains active for private individual research: `true`
- PIT-lite exploratory U50/U100 execution authorization: `none`
- Premium recommendation: `MAINTAIN_UNTIL_EXPLORATION_COMPLETE`
- Post-exploration action:
  `CONFIRM_REQUIRED_DELETION_THEN_DECIDE_STANDARD_OR_CANCELLATION`
- Real-money canary authorization: `none`

No unweighted status count is treated as proof that a provider meets the
contract. `AVAILABLE` receives credit only for its stated scope; `PARTIAL`
does not pass a critical requirement. QUICK documents the largest set of
Japan-specific selection fields, but only for its published 2014/2015-start
history. Bloomberg separately has the strongest public enterprise PIT
framing—investable-universe workflows, active/inactive companies, timestamps,
adjusted pricing, and connected reference data—but its public materials do
not establish the required Japan-specific exchange-state fields, exact daily
known-at semantics, retention rights, or derived-result rights.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| `AVAILABLE` | Allowed official evidence directly documents the required capability within the stated period/scope. |
| `PARTIAL` | Allowed official evidence documents related capability, but period, population, field semantics, or completeness is insufficient for the frozen contract. |
| `NOT_AVAILABLE` | Allowed official evidence or the frozen prior gate identifies the capability as absent. |
| `SUPPORT_CONFIRMATION_REQUIRED` | The public material does not establish the requirement. No inference is made. |
| `QUOTE_REQUIRED` | No applicable public price was found. No quote was requested. |
| `NOT_APPLICABLE` | The comparison item does not apply to the option as sold. |

`AVAILABLE` is not a license conclusion. Retention, publication, aggregate,
hash, and redistribution rights are evaluated separately.

Written-support clarification statuses used only for J-Quants Personal
Premium V2:

| Status | Meaning |
| --- | --- |
| `AVAILABLE_WHILE_SUBSCRIPTION_ACTIVE` | Authorized encrypted local storage is limited to the active Premium subscription and private personal analysis. |
| `AVAILABLE_WITH_PRIVATE_USE_BOUNDARY` | The listed raw-free outputs may be retained and published, but continuous or repeated third-party provision is outside private use. |
| `DELETION_REQUIRED` | Data outside the new plan, including copies and backups, must be deleted on downgrade. |
| `DELETE_ALL_LICENSED_AND_RECONSTRUCTIBLE_DATA` | Licensed raw and reconstructible data, copies, and backups must be deleted after the paid period or withdrawal. |
| `AVAILABLE_BY_KNOWN_CODE` | A known delisted code can be used to request its listed-period data. |
| `POPULATION_COMPLETENESS_NOT_CONFIRMED` | No complete population of all delisted issues is guaranteed. |

These statuses are not extrapolated to J-Quants Pro or any other provider.

## Compared options

| ID | Option | Publicly described delivery |
| --- | --- | --- |
| `JQ_PERSONAL` | J-Quants Personal Premium | Individual REST API; up to the service's full offered period |
| `JQ_PRO` | J-Quants Pro: Listed Issue + Stock Prices + Corporate Action | Corporate REST/SFTP/Snowflake mix |
| `JPX_DIRECT` | JPX direct Master File + O/H/L/C Price + Corporate Action | Contracted Web/FTP/SFTP files |
| `JPX_DATACUBE` | J-Quants DataCube historical files | One-off downloadable files for individuals or corporates |
| `QUICK` | QUICK Data Files/APIs: stock master + scheduled corporate action + regulatory + prices | Daily/intraday files and APIs |
| `NIKKEI_NEEDS` | Nikkei NEEDS FinancialQUEST/BULK: listed equities + domestic security attributes + corporate finance | Browser download or bulk delivery |
| `TOYO_TREND3EPOT` | Toyo Keizai TREND3EPOT + Stock Prices/Shares and optional affiliates data | Point-in-time relational database updates via FTP |
| `LSEG` | LSEG DataScope/TSE/Corporate Actions/PermID bundle | Enterprise files, APIs, data delivery |
| `BLOOMBERG` | Bloomberg Data License + PIT research + reference/pricing bundle | Enterprise bulk/files/cloud/API |
| `FACTSET` | FactSet Pricing & Reference + DMS + Global Prices/Returns/RBICS | Enterprise feeds, APIs, cloud delivery |
| `DATA_GET2` | DATA-GET2 daily CSV and long-history archive | Individual download and one-off archive |

## A. Point-in-time universe and identity

| Option | Point-in-time active issue universe | Delisted issues | Listing / delisting dates | Ticker lineage / stable security ID |
| --- | --- | --- | --- | --- |
| `JQ_PERSONAL` | `AVAILABLE` — date-scoped listed-issue snapshots, earliest service date 2008-05-07 | `PARTIAL` — `AVAILABLE_BY_KNOWN_CODE`; listed-period data can be requested when the code is known, but `POPULATION_COMPLETENESS_NOT_CONFIRMED` | `PARTIAL` overall because snapshot boundaries can be inferred, but the dedicated listing/delisting-date history API is `NOT_AVAILABLE` | `NOT_AVAILABLE` — written clarification confirms no dedicated code-change history or permanent security ID |
| `JQ_PRO` | `AVAILABLE` — historical Listed Issue Information from 2008-05-07 | `PARTIAL` — delisting events are documented, but non-dividend corporate-action history begins 2015-05-08 | `PARTIAL` — delisting and security-master change events are documented; full listing intervals back to 2008 are not | `PARTIAL` — `CodeBeforeChange` supports code lineage, but a permanent security ID is not documented |
| `JPX_DIRECT` | `PARTIAL` — next-business-day all-exchange domestic issue master; historical snapshot entitlement is not public | `PARTIAL` — corporate-action/security-master changes include delisting, but searchable public history is limited | `PARTIAL` — event/effective dates exist, but full historical interval availability is not public | `PARTIAL` — current local code/ISIN plus master changes; complete dated lineage needs confirmation |
| `JPX_DATACUBE` | `PARTIAL` — month-bounded market files can reconstruct traded issues, but this is not a formal eligible-universe master | `AVAILABLE` for purchased historical price files containing issues traded during each period | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` |
| `QUICK` | `PARTIAL` — daily stock master is explicit, but published history starts 2015-02 | `AVAILABLE` from the published 2014/2015-start master and scheduled-action histories | `AVAILABLE` from 2015-02 in the master; earlier history requires confirmation | `PARTIAL` — ISIN plus code/company change events are documented; a cross-event permanent-ID contract is not |
| `NIKKEI_NEEDS` | `PARTIAL` — domestic security basic attributes include next-business-day new listings, delistings, and attribute changes; complete historical snapshot semantics are not public | `AVAILABLE` at event-data level; completeness of a replayable daily eligible universe needs confirmation | `PARTIAL` — listing/delisting events exist, but a complete interval contract was not found | `SUPPORT_CONFIRMATION_REQUIRED` |
| `TOYO_TREND3EPOT` | `AVAILABLE` at the product-design level — official examples include selecting companies listed at any point in time | `AVAILABLE` at the product-design level — delisted companies can be selected for a specified period | `PARTIAL` — company information is generally historical from listing dates and delisting events are queryable; exact interval completeness has documented possible gaps | `PARTIAL` — records have IDs and validity/update timestamps, but permanent security-ID/code-lineage semantics need confirmation |
| `LSEG` | `PARTIAL` — DataScope covers active and retired instruments, but a daily Japan eligible-universe snapshot contract is not public | `PARTIAL` — retired instruments and delisted/relisted RIC maintenance are documented | `PARTIAL` — maintenance dates exist; complete effective listing intervals need confirmation | `PARTIAL` — PermID is persistent and RIC maintenance exists; successor/predecessor effective lineage needs confirmation |
| `BLOOMBERG` | `PARTIAL` — PIT research describes investable-universe filtering, daily snapshots, and active/inactive public companies | `PARTIAL` — active and inactive coverage is public; complete Japan population/period is not | `SUPPORT_CONFIRMATION_REQUIRED` | `PARTIAL` — FIGI is persistent and not reused, but the licensed historical lineage model needs confirmation |
| `FACTSET` | `PARTIAL` — active/inactive listings and entity/security relationships are documented; daily Japan eligibility snapshots are not | `AVAILABLE` at global product level; complete Japan population/period remains to be confirmed | `SUPPORT_CONFIRMATION_REQUIRED` | `PARTIAL` — stable FactSet IDs and current/historical identifier mapping are public; effective listing lineage needs confirmation |
| `DATA_GET2` | `NOT_AVAILABLE` — current issue information is not a point-in-time universe archive | `PARTIAL` — long-history price files include delisted issues, while the archive's current issue file excludes them | `NOT_AVAILABLE` | `NOT_AVAILABLE` |

## B. Historical eligibility attributes

| Option | Historical market / industry | Historical trading unit | Corporate-group history | Suspension / supervision / liquidation and similar history |
| --- | --- | --- | --- | --- |
| `JQ_PERSONAL` | `AVAILABLE` for effective market and 17/33-sector snapshot values; old/new regime mapping still must be frozen | `NOT_AVAILABLE` — written clarification confirms no dedicated trading-unit history API | `NOT_AVAILABLE` | `NOT_AVAILABLE` — written clarification confirms no dedicated suspension, supervision, liquidation, or equivalent history API |
| `JQ_PRO` | `AVAILABLE` for effective listed-issue values and dated security-master changes within published history | `PARTIAL` — unit-change events are documented from the corporate-action history window | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` |
| `JPX_DIRECT` | `PARTIAL` — current master contains exchange section; full dated history is not public | `PARTIAL` through security-master change data; historical depth needs confirmation | `SUPPORT_CONFIRMATION_REQUIRED` | `PARTIAL` — listing status is in the master, but a complete dated archive of all exclusion states is not public |
| `JPX_DATACUBE` | `PARTIAL` — period files preserve traded-market context, but formal classification history is not established | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` |
| `QUICK` | `AVAILABLE` from 2015-02 for exchange/section/listing classification and industry | `AVAILABLE` from 2015-02; unit-change events are also documented from 2014-12 | `PARTIAL` — company reorganization events are documented, but a dated ultimate-parent/group identifier is not | `AVAILABLE` from 2014-12 for the published regulatory/master fields, including supervision/liquidation post, special caution, trading suspension, and restrictions |
| `NIKKEI_NEEDS` | `PARTIAL` — long company/security attribute history is public, but the exact TSE regime/33-sector as-of fields need confirmation | `SUPPORT_CONFIRMATION_REQUIRED` | `PARTIAL` — company attributes include parent-company codes, but point-in-time group semantics need confirmation | `SUPPORT_CONFIRMATION_REQUIRED` |
| `TOYO_TREND3EPOT` | `AVAILABLE` at the design level for point-in-time company attributes, sector membership, and long 33-sector history | `SUPPORT_CONFIRMATION_REQUIRED` | `PARTIAL` — a separate affiliates database documents parent/subsidiary relationships; historical effective-date coverage and integration into the required universe need confirmation | `SUPPORT_CONFIRMATION_REQUIRED` |
| `LSEG` | `SUPPORT_CONFIRMATION_REQUIRED` for TSE regime/33-sector/common-share history | `SUPPORT_CONFIRMATION_REQUIRED` | `PARTIAL` — PermID links listings, issuers, subsidiaries, and parents; effective historical group membership is not public | `SUPPORT_CONFIRMATION_REQUIRED` |
| `BLOOMBERG` | `SUPPORT_CONFIRMATION_REQUIRED` for historical TSE segment/sector/common-share eligibility despite global classification products | `SUPPORT_CONFIRMATION_REQUIRED` | `PARTIAL` — corporate/capital-structure hierarchy is public; point-in-time group membership is not | `SUPPORT_CONFIRMATION_REQUIRED` |
| `FACTSET` | `PARTIAL` — RBICS and security-type history are public; TSE segment/33-sector history is not | `SUPPORT_CONFIRMATION_REQUIRED` | `PARTIAL` — DMS relationships and hierarchies “through time” are public; the required Japanese group definition/effective dates are not | `SUPPORT_CONFIRMATION_REQUIRED` |
| `DATA_GET2` | `PARTIAL` — current 33-sector code and exchange price history only | `PARTIAL` — current unit shares are provided, not a dated unit history | `NOT_AVAILABLE` | `NOT_AVAILABLE` |

## C. Corporate actions, prices, and known-at reality

| Option | Comprehensive corporate actions | Raw / adjusted OHLCV | Trading value | Known-at / publication timestamp |
| --- | --- | --- | --- | --- |
| `JQ_PERSONAL` | `PARTIAL` — split and reverse-split effects are partially observable through `AdjFactor`; a comprehensive corporate-action history API is `NOT_AVAILABLE` | `AVAILABLE` fields from 2008-05-07, subject to documented adjustment exclusions | `AVAILABLE` | `NOT_AVAILABLE` — effective date is not a versioned publication timestamp |
| `JQ_PRO` | `PARTIAL` — broad event taxonomy, but cash-dividend history starts 2013-02-20 and other events 2015-05-08 | `AVAILABLE` raw/adjusted OHLC and volume from 2008-05-07 | `AVAILABLE` | `PARTIAL` — event announcement dates/times and update schedules exist, but no complete versioned availability contract is public |
| `JPX_DIRECT` | `PARTIAL` — broad golden-source event set; searchable Web history is two years for most events and ten years for security-master changes | `PARTIAL` — direct daily raw O/H/L/C is available; an adjusted history/factor contract is not public | `AVAILABLE` in direct O/H/L/C service | `PARTIAL` — corporate actions are generally delivered promptly after disclosure, but a replayable full version history is not public |
| `JPX_DATACUBE` | `NOT_AVAILABLE` as a comprehensive event service | `PARTIAL` — official historical O/H/L/C and volume files; adjusted series is not documented in the cited catalog | `AVAILABLE` | `NOT_AVAILABLE` |
| `QUICK` | `PARTIAL` — broad Japan-specific actions from 2014-12; earlier completeness and revision history need confirmation | `PARTIAL` — raw historical bars are public; adjusted-series/factor scope is not | `AVAILABLE` at product/API level; exact selected feed fields need confirmation | `PARTIAL` — delivery times are public, but replayable arrival/revision timestamps are not |
| `NIKKEI_NEEDS` | `PARTIAL` — corporate-finance events including splits, issues, mergers, company splits, and buybacks are public from 1970; complete action taxonomy/revisions need confirmation | `AVAILABLE` at catalog level for daily prices and rights-adjusted prices | `AVAILABLE` at catalog level | `PARTIAL` — next-business-day security changes are documented, but version/revision timestamps are not |
| `TOYO_TREND3EPOT` | `PARTIAL` — stock-price adjustment factors are available, but a comprehensive corporate-action event service is not established | `AVAILABLE` at product-design level for daily price history and point-in-time adjusted-price calculation | `SUPPORT_CONFIRMATION_REQUIRED` | `PARTIAL` — relational records carry validity, insert, and last-update timestamps, but exact vendor-publication/arrival semantics require confirmation |
| `LSEG` | `PARTIAL` — 50+ equity event types, 25+ years, frequent updates; Japan completeness/revision history needs confirmation | `PARTIAL` — long TSE history, raw delivery and factors are documented; a single-version raw/adjusted daily contract needs confirmation | `SUPPORT_CONFIRMATION_REQUIRED` for the selected daily package | `PARTIAL` — point-in-time pricing and update timing do not prove known-at universe/security-master history |
| `BLOOMBERG` | `PARTIAL` — 50+ event types/global analyst coverage; Japan completeness/revisions need confirmation | `PARTIAL` — historical and corporate-action-adjusted pricing are public; exact raw OHLCV/turnover package needs confirmation | `SUPPORT_CONFIRMATION_REQUIRED` | `PARTIAL` — PIT history, timestamps and daily snapshots are public; per-field Japan known-at semantics need confirmation |
| `FACTSET` | `PARTIAL` — unified actions and adjustment workflows are public; Japan event completeness/revisions need confirmation | `AVAILABLE` at product level for unadjusted daily price/open/high/low/volume/VWAP/turnover plus adjustment workflows | `AVAILABLE` at product level | `SUPPORT_CONFIRMATION_REQUIRED` for the security-master/corporate-action known-at contract |
| `DATA_GET2` | `PARTIAL` — split/consolidation file only | `PARTIAL` — raw daily O/H/L/C/volume; no documented adjusted series | `NOT_AVAILABLE` in the cited daily specification | `NOT_AVAILABLE` — a daily update time is not a historical publication-version timestamp |

## D. Reproducibility and legal use

| Option | Version freeze / long-term retention | Store aggregate results / hashes | Redistribution / derived-result restrictions |
| --- | --- | --- | --- |
| `JQ_PERSONAL` | `PARTIAL` overall; `AVAILABLE_WHILE_SUBSCRIPTION_ACTIVE` for encrypted local storage of authorized data with acquisition date/conditions for private personal analysis. This is not post-cancellation retention | `AVAILABLE_WITH_PRIVATE_USE_BOUNDARY` for CAGR, maximum DD, win rate, PF, counts/period/missing counts, non-reconstructive SHA-256, methods, code, and raw-free backtest aggregates | `PARTIAL`; the listed raw-free outputs may be retained and published within `AVAILABLE_WITH_PRIVATE_USE_BOUNDARY`, but continuous or repeated third-party provision/distribution is outside private use |
| `JQ_PRO` | `PARTIAL` — obtained information may continue for internal use after ordinary termination, but formal snapshot/version rights remain unconfirmed | `SUPPORT_CONFIRMATION_REQUIRED` | `PARTIAL` — external-use mechanisms exist; the intended edited/processed outputs are `SUPPORT_CONFIRMATION_REQUIRED` and JPXI reserves classification |
| `JPX_DIRECT` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` — usage tiers are public, but repository outputs and termination retention are not settled |
| `JPX_DATACUBE` | `PARTIAL` technically because purchased files are fixed; legal retention and termination treatment still require confirmation | `SUPPORT_CONFIRMATION_REQUIRED` | `PARTIAL` — self-use/external/individual-academic classes exist; intended derived artifacts are `SUPPORT_CONFIRMATION_REQUIRED` |
| `QUICK` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` — secondary-use concepts are public, but the exact research-output permission is not |
| `NIKKEI_NEEDS` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` — raw retention, repository outputs, and derived-publication rights are not public |
| `TOYO_TREND3EPOT` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` — sales terms can constrain included data and no output/retention safe harbor is public |
| `LSEG` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` — dataset permissioning and third-party terms apply |
| `BLOOMBERG` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` — OpenFIGI rights do not imply rights in commercial Data License fields |
| `FACTSET` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` — supplier-specific terms can apply |
| `DATA_GET2` | `PARTIAL` for the physical/archive product only | `NOT_AVAILABLE` under the published individual terms without a separate written permission | `NOT_AVAILABLE` — published terms prohibit commercial use, independent processing/duplication, and third-party provision |

### J-Quants Personal Premium lifecycle duties

- Premium to Standard: `DELETION_REQUIRED`. Data outside the Standard plan,
  together with its copies and backups, must be deleted and cannot be used
  after the change.
- End of the paid period or membership withdrawal:
  `DELETE_ALL_LICENSED_AND_RECONSTRUCTIBLE_DATA`. Licensed raw data,
  reconstructible processed data, copies, and backups must be deleted.
- Raw-free aggregates and backtest results, non-reconstructive hashes,
  analysis methods, and program code are outside that cancellation deletion
  set.

## E. Contract availability, price, and minimum term

Prices below are public list prices only. They are not quotes or total-cost
estimates. Taxes, historical backfill, delivery, infrastructure, user counts,
affiliate use, redistribution, and separately licensed content can change the
total.

| Option | Individual | Sole proprietor | Small corporation | Public price or `QUOTE_REQUIRED` | Minimum term |
| --- | --- | --- | --- | --- | --- |
| `JQ_PERSONAL` | `AVAILABLE` for noncommercial personal own use | `NOT_AVAILABLE` for a commercial business use case | `NOT_AVAILABLE` | JPY 16,500/month including tax for Premium | Monthly; cancellation at billing-period end |
| `JQ_PRO` | `NOT_AVAILABLE` | `NOT_AVAILABLE` when the contracting person is not a legal entity | `AVAILABLE` in principle for a legal entity, subject to provider acceptance | Public single-entity subtotal: Listed Issue 50,000 + Stock Prices 150,000 + Corporate Action 300,000 = JPY 500,000/month excluding tax; with the published one-year minimum this implies a JPY 6,000,000 minimum public subtotal, excluding tax and additions | `AVAILABLE` — one year for Listed Issue, Stock Prices, and Corporate Action |
| `JPX_DIRECT` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` — a single-entity contract exists, but public materials do not confirm small-company acceptance | Indicative current-feed subtotal for “other” single-entity CA: Master 50,000 + O/H/L/C 84,000 + CA 150,000 = JPY 284,000/month excluding tax. Financial-institution CA would make the subtotal JPY 384,000. Historical backfill/rights excluded | `SUPPORT_CONFIRMATION_REQUIRED` |
| `JPX_DATACUBE` | `AVAILABLE` | `SUPPORT_CONFIRMATION_REQUIRED` | `AVAILABLE` | Example TSE all-stock O/H/L/C: individual/academic JPY 990 per month of post-2012 data and JPY 11,880 per pre-2012 year; self-use JPY 26,400/month and JPY 316,800/pre-2012 year, including tax | One-off file purchases; no subscription minimum |
| `QUICK` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `QUOTE_REQUIRED` | Monthly service is public; minimum duration is `SUPPORT_CONFIRMATION_REQUIRED` |
| `NIKKEI_NEEDS` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` — the service is corporate-oriented, but small-company acceptance is not public | `QUOTE_REQUIRED` | The applicable minimum is `SUPPORT_CONFIRMATION_REQUIRED` |
| `TOYO_TREND3EPOT` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `QUOTE_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` |
| `LSEG` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `QUOTE_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` |
| `BLOOMBERG` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `QUOTE_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` |
| `FACTSET` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` | `QUOTE_REQUIRED` | `SUPPORT_CONFIRMATION_REQUIRED` |
| `DATA_GET2` | `AVAILABLE` | `NOT_AVAILABLE` for commercial use under the cited terms | `NOT_AVAILABLE` | JPY 2,200/month including tax for daily CSV; JPY 16,500 including tax for the long-history archive | Monthly auto-renewal or one-off archive purchase |

## Formal U50/U100 classification

| Option | Current Formal status | Why it stops |
| --- | --- | --- |
| `JQ_PERSONAL` | `NOT_POSSIBLE_ALONE` | Written clarification permits bounded PIT-lite private exploration but does not provide a complete delisted population, direct listing/delisting history, code lineage/permanent ID, trading-unit history, special-status history, or comprehensive corporate-action history |
| `JQ_PRO` | `CONDITIONAL_HYBRID_CANDIDATE` | Corporate group, special-status history, full-period lineage/listing intervals, complete known-at semantics, and research rights remain unresolved |
| `JPX_DIRECT` | `CONDITIONAL_HYBRID_CANDIDATE` | Current-feed prices do not establish historical point-in-time backfill or full archive rights |
| `JPX_DATACUBE` | `NOT_POSSIBLE_ALONE` | Strong price history, but not the missing eligibility/security-state plane |
| `QUICK` | `CONDITIONAL_HYBRID_CANDIDATE` | Japan-specific fields are strong, but published master/regulatory history begins only in 2014/2015 and license/known-at details are unresolved |
| `NIKKEI_NEEDS` | `CONDITIONAL_HYBRID_CANDIDATE` | Long Japan price/action coverage is strong, but the exact point-in-time eligible-universe, state-history, stable-ID, known-at, and license contract is unresolved |
| `TOYO_TREND3EPOT` | `LEADING_DOMESTIC_PIT_CONDITIONAL_CANDIDATE` | Explicit PIT design and long prices are strong, but trading-unit/status history, comprehensive actions, permanent identity, and output rights remain unresolved |
| `LSEG` | `CONDITIONAL_FORMAL_CANDIDATE` | Japan-specific eligibility/status/unit fields and snapshot/output rights remain unresolved |
| `BLOOMBERG` | `ENTERPRISE_PIT_CONDITIONAL_CANDIDATE` | Strong public PIT framing, but Japan-specific fields, exact known-at contract, and license rights remain unresolved |
| `FACTSET` | `CONDITIONAL_FORMAL_CANDIDATE` | Strong prices/IDs/entity history, but PIT security-master known-at and Japan-specific eligibility states remain unresolved |
| `DATA_GET2` | `NOT_POSSIBLE` | Missing data dimensions plus incompatible published processing/use terms |

No row is a Formal Candidate approval. `formal_u50_u100_possible` remains
`false` until a separate written data-reality gate proves every critical
field, period, version, and license requirement against sample
documentation/data under an approved trial or contract.

The support clarification changes PIT-lite exploratory readiness only.
It does not change Formal U50/U100 status, execution authorization, or
real-money canary authorization. PIT-lite execution also requires separate
explicit approval.

## Evidence register

The comparative source links below were publicly accessible without using a
provider account during this desk review. J-Quants Personal Premium V2 also
uses an official written support clarification received in 2026-07. Repository
evidence is limited to the non-verbatim summary in
`JQUANTS_SUPPORT_CLARIFICATION_2026_07.md`; the original message and all
personal/contact information are not retained.

### J-Quants and JPX

1. J-Quants Personal overview, plans, and FAQ:
   https://jpx-jquants.com/?lang=ja%2F
2. Personal Listed Issue Master:
   https://jpx-jquants.com/ja/spec/eq-master
3. Personal daily bars:
   https://jpx-jquants.com/ja/spec/eq-bars-daily
4. Personal adjustment logic:
   https://jpx-jquants.com/ja/spec/eq-bars-daily/adj
5. Personal data periods:
   https://jpx-jquants.com/ja/spec/data-spec
6. Personal terms:
   https://jpx-jquants.com/ja/termsofservice
7. J-Quants Pro Listed Issue Information:
   https://pro.jpx-jquants.com/datasets/4
8. J-Quants Pro Stock Prices:
   https://pro.jpx-jquants.com/datasets/9
9. J-Quants Pro Corporate Action Data:
   https://pro.jpx-jquants.com/datasets/14
10. J-Quants Pro pricing and usage appendix:
    https://pro.jpx-jquants.com/pdfs/appendix-1-2-pricing-and-usage-table-en.pdf
11. J-Quants Pro license:
    https://pro.jpx-jquants.com/pdfs/j-quants-pro-data-license-agreement-en.pdf
12. J-Quants Pro security-master change schema:
    https://jpx.gitbook.io/j-quants-pro-ja/api-reference/corporate_action/change_of_stock_detail
13. J-Quants Pro delisting schema:
    https://jpx.gitbook.io/j-quants-pro-ja/api-reference/corporate_action/delisting
14. JPX direct Reference Data / Master File:
    https://www.jpx.co.jp/english/markets/paid-info-equities/reference/08.html
15. JPX Corporate Action Data Service:
    https://www.jpx.co.jp/english/markets/paid-info-listing/corporate-action/index.html
16. JPX historical data and delivery comparison:
    https://www.jpx.co.jp/english/markets/paid-info-equities/historical/
17. J-Quants DataCube overview:
    https://www.jpx.co.jp/markets/other-data-services/j-quants-datacube/index.html
18. J-Quants DataCube public price list:
    https://db-ec.jpx.co.jp/client_info/JPX_DLSITE/html/datacube_price.pdf
19. J-Quants DataCube terms:
    https://db-ec.jpx.co.jp/client_info/JPX_DLSITE/html/kiyaku.pdf
20. J-Quants DataCube data specification:
    https://db-ec.jpx.co.jp/client_info/JPX_DLSITE/html/data_detail.pdf
21. JPX Reference Data fee schedule:
    https://www.jpx.co.jp/english/markets/paid-info-equities/reference/tvdivq00000024wc-att/e_fee_schedule_ref_data.pdf

### QUICK

22. QUICK data services:
    https://corporate.quick.co.jp/products/data/
23. QUICK APIs:
    https://corporate.quick.co.jp/products/quick-apis/
24. QUICK stock master:
    https://corporate.quick.co.jp/data-factory/product/data013/
25. QUICK scheduled corporate-action file:
    https://corporate.quick.co.jp/data-factory/product/data014/
26. QUICK regulatory file:
    https://corporate.quick.co.jp/data-factory/product/data015/

### Nikkei NEEDS and Toyo Keizai

27. Nikkei NEEDS data catalog:
    https://needs.nikkei.co.jp/needs-data/
28. Nikkei NEEDS FinancialQUEST:
    https://needs.nikkei.co.jp/services/financial-quest/
29. Nikkei NEEDS BULK:
    https://needs.nikkei.co.jp/services/bulk/
30. Toyo Keizai TREND3EPOT:
    https://biz.toyokeizai.net/en/data/service/detail/id=1204
31. TREND3EPOT official overview:
    https://biz.toyokeizai.net/files/user/data_doc/pdf/TRENDE3EPOT_OVERVIEW.pdf
32. Toyo Keizai affiliates data:
    https://biz.toyokeizai.net/en/data/service/detail/id=866
33. Toyo Keizai database pricing/inquiry process:
    https://biz.toyokeizai.net/data/news/detail/id=3463

### LSEG / Refinitiv

34. Tokyo Stock Exchange data:
    https://www.lseg.com/en/data-analytics/financial-data/pricing-and-market-data/equities-market-data/tokyo-stock-exchange-data
35. DataScope Select delivery:
    https://www.lseg.com/en/data-analytics/products/datascope-select-data-delivery
36. Corporate Actions:
    https://www.lseg.com/en/data-analytics/market-data/data-analytics-pricing/reference-data/corporate-actions
37. DataScope Select User Guide:
    https://developers.lseg.com/content/dam/devportal/api-families/datascope-select/datascope-select-rest-api/documentation/overview-and-concepts/dss_14_5_user_guide.pdf
38. PermID FAQ:
    https://permid.org/faq
39. PermID terms:
    https://permid.org/terms

### Bloomberg

40. Bloomberg Data License:
    https://professional.bloomberg.com/products/data/data-management/data-license/
41. Bloomberg Reference Data:
    https://professional.bloomberg.com/products/data/enterprise-catalog/reference/
42. Bloomberg Company Financials, Estimates & Pricing:
    https://professional.bloomberg.com/products/data/enterprise-catalog/cofi/
43. Bloomberg Investment Research Data:
    https://professional.bloomberg.com/products/data/enterprise-catalog/investment-research-data/
44. OpenFIGI overview:
    https://www.openfigi.com/about/overview
45. OpenFIGI terms:
    https://www.openfigi.com/docs/terms-of-service

### FactSet

46. FactSet Pricing and Reference Data:
    https://www.factset.com/marketplace/catalog/product/factset-pricing-and-reference-data
47. FactSet Global Prices API:
    https://developer.factset.com/api-catalog/factset-global-prices-api
48. FactSet Prices and Returns API:
    https://www.factset.com/marketplace/catalog/product/factset-prices-and-returns-api
49. FactSet Data Management Solutions:
    https://www.factset.com/marketplace/catalog/product/factset-data-management-solutions
50. FactSet Entity API:
    https://developer.factset.com/api-catalog/factset-entity-api
51. FactSet RBICS API:
    https://developer.factset.com/api-catalog/factset-rbics-api
52. FactSet third-party terms:
    https://www.factset.com/third-party-terms

### Individual-access alternative

53. DATA-GET2 individual daily service:
    https://www.data-get2.jp/general/service.html
54. DATA-GET2 daily specification:
    https://www.data-get2.jp/general/dl.html
55. DATA-GET2 long-history archive:
    https://www.data-get2.jp/general/cd.html
56. DATA-GET2 price:
    https://www.data-get2.jp/general/price.html
57. DATA-GET2 terms:
    https://www.data-get2.jp/kiyaku.html
58. J-Quants Pro minimum usage periods:
    https://pro.jpx-jquants.com/pdfs/appendix-1-3-other-notes-en.pdf
59. J-Quants Pro external distribution:
    https://pro.jpx-jquants.com/pdfs/appendix-4-external-distribution-en.pdf

## Non-actions confirmed

- Written support clarification stored as a non-verbatim summary: yes
- Original email or personal/contact data stored: no
- Existing Premium recommendation: maintain until the separately approved
  exploratory phase is complete
- New contract, purchase, or plan change: none
- Quote approval or quote request: none
- New provider contact in this amendment: none
- Provider API access: none
- Raw or sample data acquired: none
- Formal U50/U100 possible: false
- PIT-lite exploratory U50/U100 possible while Premium is active: true
- PIT-lite exploratory U50/U100 execution authorization: none
- U50/U100 backtest: not executed
- Real-money canary authorization: none
- Production, Cloudflare, GitHub Actions production workflow, Google Sheets,
  Secrets, LINE, pending, and trading path changes: none
