# J-Quants Premium Capability Audit

## Audit identity

- Gate: V2-R1B Data & Portfolio Reality Gate
- Audit date: 2026-07-26
- Base commit: `52ead3fe27c67da60d8eede4bc38fd1b4311f8ce`
- API: J-Quants personal API V2
- Authentication: `JQUANTS_API_KEY` via `x-api-key`; successful; secret not
  recorded
- API attempts used: 10 / 30
- Successful API responses: 9 HTTP 200
- Prior failed attempt: 1 TLS attempt before an HTTP response
- Hidden retries: 0
- Full-market full-history download: none
- Large CSV download: none
- Raw response retained: none
- U50/U100 backtest: not executed
- Capability verdict: `PRO_OR_ALTERNATIVE_REQUIRED`

The failed TLS attempt was counted conservatively against the 30-request
budget. The successful run retained certificate verification and used the
system CA bundle; verification was not disabled.

## Executive conclusion

The personal Premium API can build effective-date active-issue snapshots from
2008-05-07 onward and can supply raw daily OHLCV, traded value, and adjustment
fields. The bounded live probe verified split/reverse-split factors but not
comprehensive corporate-action coverage. It also verified one later-delisted
issue in a historical snapshot and its pre-delisting bars.

It cannot, by itself, implement the frozen Formal U50/U100 contract. The
personal V2 master does not expose dated listing/delisting intervals, trading
unit, ticker lineage or a stable security ID, dated corporate-group mapping,
or a sufficient special-treatment/untradeable status. Its effective `Date`
does not provide a versioned known-at timestamp. Long-term reproducible raw
snapshot retention/publication also needs written support clarification.

Formal U50/U100 remains stopped. A current static universe would remain
survivorship-biased exploratory evidence.

## Method and safety

The fixed plan made five `/equities/master` requests and four bounded
`/equities/bars/daily` requests. Pagination was supported with a maximum of
three pages per logical probe, but each live probe completed in one page.
Every attempt was counted before dispatch, requests were single-threaded and
spaced by at least one second, and no automatic retry was enabled.

Response bodies were temporarily stored below a random `/tmp/tgs-jquants-v2-*`
directory, parsed, hashed, and deleted in a `finally` block. Nine temporary raw
files were created and zero were retained. No temporary probe directory
remained after the audit.

Committed JSON contains only endpoint/parameter metadata, fields, counts,
null counts, min/max dates, HTTP status codes, byte counts, SHA-256 hashes, and
bounded derived metrics. It contains no full issue list, company name,
raw-price value, OHLCV row, response body, credential, or authentication
header value.

## A. Listed Issue Master

Endpoint: `GET /v2/equities/master`

| Requested point | Response date | Rows | Pages | Status |
| --- | --- | ---: | ---: | --- |
| 2010-04-01 | 2010-04-01 | 2,443 | 1 | `ok` |
| 2015-04-01 | 2015-04-01 | 3,747 | 1 | `ok` |
| 2020-04-01 | 2020-04-01 | 4,031 | 1 | `ok` |
| 2025-04-01 | 2025-04-01 | 4,411 | 1 | `ok` |
| no date / latest available | 2026-07-27 | 4,444 | 1 | `ok` |

The audit ran on Sunday 2026-07-26. The no-date request returned the next
business-day snapshot dated 2026-07-27, consistent with the documented
Light-or-higher next-business-day behavior. Formal research must use explicit
selection dates rather than assume no-date means the latest completed trading
session.

Observed fields in every snapshot:

`Date`, `Code`, `CoName`, `CoNameEn`, `S17`, `S17Nm`, `S33`, `S33Nm`,
`ScaleCat`, `Mkt`, `MktNm`, `Mrgn`, `MrgnNm`, `ProdCat`.

All observed master fields had zero JSON null values in all five snapshots;
the audit did not separately normalize blank strings or categorical
placeholders. The repository stores the per-snapshot field-level null counts
and a SHA-256 of each raw response and sorted code set, but not the issue
values.

Findings:

- historical date parameter: `AVAILABLE`;
- effective-date active issue snapshot: `AVAILABLE`;
- market classification: `AVAILABLE`;
- 17/33 sector classification: `AVAILABLE`;
- security product category: `PARTIAL` (`ProdCat` does not by itself prove
  ordinary/common share class);
- historical market-regime mapping: `PARTIAL`;
- listing date: `PARTIAL` (not a field; only potentially derivable from dense
  first-presence snapshots);
- delisting date: `PARTIAL` (not a field; only potentially derivable from dense
  last-presence snapshots);
- trading unit: `NOT_AVAILABLE`;
- code-change lineage / stable security ID: `NOT_AVAILABLE`;
- corporate-group mapping: `NOT_AVAILABLE`;
- sufficient special-treatment/untradeable status: `NOT_AVAILABLE`;
- known-at / available-at version timestamp: `NOT_AVAILABLE`.

Official documentation says a non-business date maps to the next business-day
snapshot. The service-wide earliest master/price date is 2008-05-07; requesting
an earlier Premium date returns that earliest snapshot rather than the true
earlier universe.

## B. Daily Bars

Endpoint: `GET /v2/equities/bars/daily`

Observed fields included:

- raw daily: `O`, `H`, `L`, `C`, `Vo`, `Va`;
- limits: `UL`, `LL`;
- adjustment: `AdjFactor`, `AdjO`, `AdjH`, `AdjL`, `AdjC`, `AdjVo`;
- Premium morning fields: `MO`, `MH`, `ML`, `MC`, `MVo`, `MVa` and adjusted
  variants;
- Premium afternoon fields: `AO`, `AH`, `AL`, `AC`, `AVo`, `AVa` and
  adjusted variants.

| Bounded example | Official action | Rows / date range | Factor evidence | Continuity result |
| --- | --- | --- | --- | --- |
| 8697 | 1-for-2 split, effective 2024-10-01 | 9 / 2024-09-24–2024-10-04 | min 0.5, max 1, one non-one row | normalized raw gap 1.03157895; adjusted gap 1.03157895; pass |
| 7011 | 1-for-10 split, effective 2024-04-01 | 10 / 2024-03-25–2024-04-05 | min 0.1, max 1, one non-one row | normalized raw gap 1.00891199; adjusted gap 1.00891199; pass |
| 8411 | 10-for-1 reverse split, effective 2020-10-01 | 11 / 2020-09-23–2020-10-07 | min 1, max 10, one non-one row | normalized raw gap 0.9775321; adjusted gap 0.9775321; pass |

The codes were selected from official JPX corporate-action notices, not
guessed from returns. The continuity check stores no prices: it compares the
raw opening gap with the reported factor, then checks the adjusted opening
against the prior adjusted close. Each ratio was within a deliberately broad
25% market-movement tolerance.

The 8411 sample includes the documented 2020-10-01 all-market halt. One row
had null raw/adjusted OHLC, volume, and traded value, while the other bounded
samples had zero nulls. The exact per-field null counts are in the sanitized
summary.

Official adjustment semantics:

- prices are adjusted backward using cumulative future adjustment factors;
- documented adjustment scope includes splits, reverse splits, and rights
  issues;
- volume is not adjusted for rights issues, and foreign-stock/TOKYO PRO MARKET
  rights issues can remain `AdjFactor=1`;
- dividends are not included in adjusted prices;
- some actions are outside the adjustment logic;
- Premium provides separate dividend facts, but not a precomputed
  dividend-inclusive total-return series.

Therefore:

- daily raw OHLCV: `AVAILABLE`;
- traded value (`Va`): `AVAILABLE`;
- adjustment factor: `PARTIAL` (three split/reverse-split examples verified;
  comprehensive action coverage not established);
- adjusted price/volume fields: `AVAILABLE` as fields, subject to the documented
  action-specific limitations;
- dividend-return identification: `PARTIAL`.

The separate Premium dividend dataset begins 2013-02-20, so it cannot by
itself provide dividend facts for the entire 2008-start common price period.

## C. Delisted issue

JPX publicly announced that code 7829 would be delisted on 2024-06-27.
The live audit found its five-digit API code:

- present in the 2020-04-01 master: yes;
- present in the latest master: no;
- bounded daily bars available through 2024-06-26: yes.

This verifies that this later-delisted issue can be represented by an earlier
date-scoped master and that its bounded historical bars remain queryable.
One example cannot establish population-wide completeness, so
`delisted_issue_inclusion` is `PARTIAL`.

It does not provide the missing delisting-date field or general ticker
lineage. The official public notice supplied the date for this example; a
formal all-issue pipeline cannot scrape one-off notices as a substitute for a
licensed dated interval table without a separate design and source gate.

## D. Legal and reproducibility classification

This is a research classification, not legal advice. The cited terms are for
the personal J-Quants API, not J-Quants Pro. The English reference says it was
last updated 2026-01-19. Article 1 makes the terms prevail over inconsistent
FAQ or other materials, and Article 24 makes the Japanese text authoritative.

| Activity | Classification | Basis |
| --- | --- | --- |
| Ephemeral local processing for personal research | available only for noncommercial, nonacademic personal own use | Required to consume the service; Terms Article 8 limits use to own use |
| Persistent/versioned local raw storage | `SUPPORT_CONFIRMATION_REQUIRED_WITH_CANCELLATION_DELETION_DUTY` | no explicit archival safe harbor; Terms Articles 7 and 15 require deletion |
| Public GitHub raw-data commit | not permitted | Internet/third-party distribution is outside own use |
| Private GitHub raw-data storage | avoid; `SUPPORT_CONFIRMATION_REQUIRED` | no clear third-party-hosting exception |
| One-time aggregate results / hashes | `SUPPORT_CONFIRMATION_REQUIRED` | FAQ presents the service for private individual analysis but provides no clear publication safe harbor; terms also cover edited/processed Data and take precedence |
| Third-party raw or continuing data distribution | not permitted | own-use restriction |
| Retention after subscription cancellation plus the remaining period, or membership cancellation | not permitted absent written exception | Terms Articles 7 and 15 require deletion of Data and duplicates on those paths |

The audit committed narrow aggregate/hash metadata because the research gate
explicitly allowed that bounded one-time scope. That scope is not a legal
conclusion and does not establish a general license safe harbor for future
snapshots or continuing publication. Written clarification is required before
a persistent formal dataset is acquired.

Official support contact: `j-quants@jpx.co.jp`.

## Capability matrix

| Capability | Status | Formal-critical |
| --- | --- | --- |
| Point-in-time active issue master | `AVAILABLE` | yes |
| Delisted issue inclusion | `PARTIAL` | yes |
| Listing date | `PARTIAL` | yes |
| Delisting date | `PARTIAL` | yes |
| Five-year listing-history eligibility | `PARTIAL` | yes |
| Historical market | `AVAILABLE` | yes |
| Historical sector | `AVAILABLE` | yes |
| Security product category | `PARTIAL` | yes |
| Historical market-regime mapping | `PARTIAL` | yes |
| Trading unit | `NOT_AVAILABLE` | no |
| Ticker lineage / stable ID | `NOT_AVAILABLE` | yes |
| Historical corporate group | `NOT_AVAILABLE` | yes |
| Special-treatment / untradeable status | `NOT_AVAILABLE` | yes |
| Daily OHLCV | `AVAILABLE` | yes |
| Traded value | `AVAILABLE` | yes |
| Adjustment factor | `PARTIAL` | yes |
| Raw and adjusted OHLC | `AVAILABLE` | no |
| Dividend return identification | `PARTIAL` | no |
| Reproducible historical snapshot | `SUPPORT_CONFIRMATION_REQUIRED` | yes |
| Known-at / available-at timestamp | `NOT_AVAILABLE` | yes |
| Full frozen U15 period coverage | `PARTIAL` | no |

Machine-readable details are in
`results/jquants_capability_matrix.json`.

## Personal Premium versus Pro

Personal Premium offers up to 20 years, with the service beginning
2008-05-07. Standard offers 10 years. The frozen U15 effective period starts
in 2004, so a full replacement is impossible from personal Premium. A
split/reverse-split-adjusted exploratory common-period U15 rerun is
technically possible but was not authorized or run.

J-Quants Pro is a separate service. Its published corporate-action schemas
include:

- `DelistingDate` for delisting events; and
- `CodeBeforeChange`, `Code`, and `EffectiveDate` for security-attribute
  changes.

The legacy corporate-action dataset is described as SFTP/Snowflake delivery
rather than personal V2 REST. Its dividend history begins 2013-02-20 and its
other event history begins 2015-05-08. The 2026 Pro catalog also lists
`Listed Shares Flash Data` and `Listed Shares Corporate Action Factors`, each
with REST/SFTP/Snowflake delivery and history from May 2008. Those newer
datasets can help with listed-share-count changes and their factors/reasons;
their published scope does not by itself establish every required
listing/delisting interval, stable identity, corporate-group mapping,
known-at timestamp for the complete point-in-time universe and its required
attributes, or archival right. Pro therefore may address some gaps but does
not automatically resolve the full-period or licensing requirements. No
paid-service change was made.

## Final decisions

- Capability verdict: `PRO_OR_ALTERNATIVE_REQUIRED`
- Premium recommendation:
  `MAINTAIN_PENDING_SUPPORT_AND_APPROVED_ARCHIVAL_GATE`
- Standard downgrade: `DO_NOT_DOWNGRADE_YET`
- Acquire/fix data before a cancellation decision: do not bulk acquire for
  retention beyond a specified cancellation path; first obtain written
  storage/publication clarification and an approved missing-attribute source
- U15 split/reverse-split-adjusted rerun: common-period capability exists;
  comprehensive corporate-action coverage and the full frozen period do not;
  execution not authorized
- Formal U50/U100 possible: no
- Formal U50/U100 authorized: no
- U50/U100 executed: no

## Required next gate

Run a separate source-and-license gate, without buying a service or running a
backtest, to obtain written J-Quants clarification and compare Pro or another
source for dated listing/delisting intervals, code lineage/stable identity,
an ordinary/common-share filter, a frozen historical market-regime mapping,
corporate-group mapping, special-treatment/tradability status, and legally
versioned snapshots. Only after those gaps are closed should a common-period
U15/U50/U100 data contract be proposed for approval.

## Official references

- Personal API master:
  https://jpx-jquants.com/ja/spec/eq-master
- Personal API daily bars:
  https://jpx-jquants.com/ja/spec/eq-bars-daily
- Personal adjustment logic:
  https://jpx-jquants.com/ja/spec/eq-bars-daily/adj
- Data periods:
  https://jpx-jquants.com/ja/spec/data-spec
- Rate limits:
  https://jpx-jquants.com/ja/spec/rate-limits
- Personal terms (English reference; Japanese text prevails):
  https://jpx-jquants.com/en/termsofservice
- Personal terms (authoritative Japanese text):
  https://jpx-jquants.com/ja/termsofservice
- Personal FAQ:
  https://jpx-jquants.com/
- JPX personal-service overview and contact:
  https://www.jpx.co.jp/markets/other-data-services/j-quants-api/index.html
- J-Quants Pro listed issue / prices / corporate action:
  https://pro.jpx-jquants.com/datasets/4,
  https://pro.jpx-jquants.com/datasets/9,
  https://pro.jpx-jquants.com/datasets/14
- Pro listed-shares flash / corporate-action factors:
  https://pro.jpx-jquants.com/datasets/16,
  https://pro.jpx-jquants.com/datasets/17
- Pro listed-shares API schemas:
  https://jpx.gitbook.io/j-quants-pro-ja/api-reference/listed_shares,
  https://jpx.gitbook.io/j-quants-pro-ja/api-reference/listed_shares_change
- JPX announcement for the 2026 Pro datasets:
  https://www.jpx.co.jp/english/corporate/news/news-releases/6020/20260120-01.html
- Pro delisting schema:
  https://jpx.gitbook.io/j-quants-pro-ja/api-reference/corporate_action/delisting
- Pro stock-detail change schema:
  https://jpx.gitbook.io/j-quants-pro-ja/api-reference/corporate_action/change_of_stock_detail
- JPX split notice for 8697:
  https://www.jpx.co.jp/corporate/news/news-releases/0063/mklp770000006msc-att/20240513_J_1.pdf
- JPX split notice for 7011:
  https://www.jpx.co.jp/english/news/2020/20240314-01.html
- JPX reverse-split notice for 8411:
  https://www.jpx.co.jp/english/news/2020/20200915-03.html
- JPX delisting notice for 7829:
  https://www.jpx.co.jp/news/1023/20240626-11.html
