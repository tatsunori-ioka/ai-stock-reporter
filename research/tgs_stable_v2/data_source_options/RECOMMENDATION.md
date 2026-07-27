# V2-R1C Data Source Recommendation

Decision date: 2026-07-27

Base commit: `4f59764cfef49f7a9c0781469d30912e7f7826b0`

Decision: `DO_NOT_BUY_YET`

Formal U50/U100 possible from current public evidence: `false`

U50/U100 execution authorization: `none`

Real-money canary authorization: `none`

## Executive decision

No compared service can be approved from public documentation alone as the
Formal U50/U100 data source. Every plausible enterprise option still has at
least one unresolved critical item: Japan-specific eligibility state,
full-period listing/code history, corporate-group history, replayable
known-at timestamps, long-term raw retention, or permission to preserve and
publish non-reconstructive results and hashes.

Do not purchase, subscribe, request a trial, connect an API, or run U50/U100
yet. The next gate should be a written scope-and-license gate using the same
field checklist for a small, ranked set of providers. A quote is useful only
after the provider answers the capability and rights questions in writing.

## Findings by requested decision

### Most requirements met

`none confirmed`

No provider receives a pass for a critical field labelled `PARTIAL` or
`SUPPORT_CONFIRMATION_REQUIRED`, so no service can truthfully be described as
meeting the most requirements. QUICK has the highest documented coverage of
Japan-specific selection fields, within its shorter public history.
Bloomberg separately has the strongest enterprise PIT framing, but that is
not evidence that it passes the Japan-specific fields.

The Bloomberg public material describes investable-universe filtering, active
and inactive companies, point-in-time history, timestamps, daily snapshots,
reference data, and adjusted pricing. It does not prove complete historical
TSE market/sector/trading-unit fields, supervision/liquidation and
trading-suspension states, complete Japan corporate-action revisions, daily
trading value, or the required retention/output rights.

### Strongest Japan-specific operational candidate

`QUICK`

The public QUICK stock master, scheduled corporate-action file, and
regulatory file directly describe the Japan-specific fields closest to the
frozen selection rules: listing/delisting dates, market/section, industry,
trading unit, supervision/liquidation post, special-caution and suspension
states, restrictions, and broad corporate events.

Its decisive limitation is published history: the relevant master starts in
February 2015 and the action/regulatory files in December 2014. That cannot
silently stand in for the full approved research period. Earlier archives,
correction vintages, price-adjustment scope, and rights all require written
confirmation.

### Strongest domestic point-in-time design

`TOYO_TREND3EPOT`

TREND3EPOT explicitly documents point-in-time selection of listed companies,
delisted-company event queries, record validity intervals, insert/update
timestamps, long price history, and point-in-time adjusted-price
calculation. It is the best documented domestic PIT design in this review.

It is still conditional because the public material does not establish the
complete trading-unit history, all TSE supervision/suspension states,
permanent security lineage, comprehensive corporate actions, trading value,
or the necessary archive and derived-output rights. Its separate affiliates
data is promising for group controls, but historical effective-date semantics
must be confirmed.

### Minimum-cost candidate

There are three different meanings of “minimum cost”:

1. Lowest public price: `DATA_GET2`, at JPY 2,200/month or JPY 16,500 for the
   long-history archive, tax included. It is not a Formal source. It lacks
   the required eligibility plane and its published individual terms prohibit
   the processing/third-party use needed by this research workflow.
2. Lowest public-price official exchange files:
   `JPX_DATACUBE`. Individual/academic all-stock O/H/L/C is publicly
   listed at JPY 990 per market month after 2012 and JPY 11,880 per
   pre-2012 market year. It is useful price evidence, not a solution for the
   missing point-in-time security-state plane.
3. Lowest public corporate bundle worth a scope inquiry:
   `JPX_DIRECT`. The current-feed public subtotal begins at
   JPY 284,000/month excluding tax for a non-financial single entity
   (Master JPY 50,000 + O/H/L/C JPY 84,000 + Corporate Action JPY 150,000).
   This excludes historical backfill, delivery, additional datasets, and the
   required output/retention rights.

J-Quants Pro's three core datasets total JPY 500,000/month excluding tax at
the published single-entity prices. Because each has a published one-year
minimum usage period, their minimum public subtotal is JPY 6,000,000 excluding
tax. That annual subtotal is an arithmetic inference, not a quote, and excludes
additional datasets, delivery, historical scope, and output/retention rights.

No minimum-cost *Formal* option can be named until the quote-required
providers answer the same field and license checklist.

### Individual-contract candidates

- J-Quants Personal Premium
- J-Quants DataCube
- DATA-GET2

None can implement Formal U50/U100. Personal J-Quants remains the approved
V2-R1B baseline finding: it is useful for substantial price/master coverage
but not sufficient alone. DataCube can provide official purchased files but
not the complete missing state plane. DATA-GET2 fails both capability and
published-use requirements.

Individual and personal-use availability must not be treated as sole
proprietor business-use permission.

### Small-corporation requirement

J-Quants Pro explicitly limits customers to legal entities, so a sole
proprietor acting as a natural person cannot contract for it under the public
license. A small corporation is eligible in principle, subject to provider
acceptance.

JPX direct, QUICK, Nikkei NEEDS, Toyo Keizai, LSEG, Bloomberg, and FactSet are
commercial or enterprise-style candidates, but their public pages do not
establish every small-company acceptance rule, minimum spend, or term.
Incorporation must not be initiated merely to seek a quote; first obtain a
non-binding written eligibility answer.

### Candidates capable of enabling Formal U50/U100

Current answer: `none confirmed`.

Conditional shortlist, not ranked:

- Bloomberg Data License/PIT bundle, if the Japan field dictionary and
  license responses pass.
- Toyo Keizai TREND3EPOT plus a confirmed Japan regulatory/corporate-action
  supplement, if identity, group, status, and output rights pass.
- QUICK bundle plus a proven pre-2015 archive and point-in-time revision
  contract.
- LSEG DataScope/TSE/Corporate Actions/PermID bundle, if the exact Japan
  eligibility and known-at fields pass.
- FactSet Pricing & Reference/DMS/Prices/RBICS bundle, if the Japan
  security-state and known-at contract passes.
- J-Quants Pro or JPX direct as a lower-cost core combined with a separately
  licensed group/status/history source.
- Nikkei NEEDS as a long-history Japan price/action core combined with a
  proven PIT identity/state source.

No hybrid should be approved until its cross-provider identity mapping,
effective-date alignment, correction policy, and common snapshot version are
specified. Combining vendors can create a new look-ahead or code-lineage
failure even when each source is individually high quality.

## Questions to send before any quote approval

Ask each shortlisted provider to answer these in writing against the exact
Japanese-equities package:

1. Can you deliver a complete daily point-in-time universe of eligible
   Japanese common shares, including later-delisted issues, for the full
   proposed research period?
2. Are listing date, delisting date, stable security ID, former/current code
   lineage, market segment, industry, and trading unit available with
   effective dates and full history?
3. How are ordinary/common shares distinguished from preferred shares,
   foreign shares, ETFs, REITs, tracking stocks, and other products at each
   historical date?
4. Can you provide dated parent/ultimate-parent or equivalent group
   relationships under a documented, stable definition suitable for
   portfolio concentration limits?
5. Can every historical supervision, liquidation, special-caution,
   trading-suspension, and otherwise untradeable state be replayed as of each
   selection date?
6. Which corporate-action event types are covered, from what date, and are
   announcement, effective, cancellation, correction, and vendor-publication
   timestamps retained?
7. Are raw and adjusted daily O/H/L/C, volume, trading value, and every
   adjustment factor available from the same frozen version?
8. Does each field have effective-at, known-at, first-publication, and
   last-revision timestamps, or an equivalent replayable vintage model?
9. May encrypted raw snapshots, schemas, and data dictionaries be retained
   indefinitely for internal reproducibility after ordinary termination?
10. May non-reconstructive aggregates, counts, performance metrics, and
    SHA-256 fingerprints be committed to a private or public research
    repository?
11. What contract category applies to an individual, sole proprietor, and
    small Japanese corporation, and what are the minimum fee and term?
12. What is the total price for the exact fields, full history, backfill,
    delivery method, one research user, internal research, and no raw-data
    redistribution?
13. What restrictions apply to derived backtest results, research reports,
    external publication, model outputs, audits, and termination-time
    deletion?
14. Will you provide a field dictionary and a tiny synthetic or legally
    reviewable sample covering a listing, delisting, code change, split,
    merger, trading-unit change, supervision designation, suspension,
    correction, and corporate-group change before commitment?

The first request should be a capability/licensing questionnaire, not a
purchase request. Do not approve a quote that answers only price.

## Is additional spend worthwhile now?

`NO`

The expected value of paying now is negative because:

- Formal U50/U100 remains blocked by contract semantics, not merely by data
  volume;
- the lowest-priced products do not close the missing eligibility fields;
- enterprise products can still fail the exact Japan state or output-rights
  requirement after purchase;
- a non-binding written questionnaire can remove most uncertainty before
  cost is incurred; and
- U15 did not pass its economic gate, so the threshold for additional data
  spend should be evidence-driven.

Additional spend becomes worth evaluating only after at least one provider
returns a complete field/period/license response and a separate gate freezes:

- the common U15/U50/U100 period;
- the provider, dataset/version and correction policy;
- identity and cross-provider mapping;
- raw versus adjusted inputs;
- snapshot/hash/retention rules;
- allowed derived outputs; and
- a maximum approved total cost and minimum term.

## Recommended next gate

`V2-R1D_WRITTEN_SCOPE_LICENSE_AND_SAMPLE_DICTIONARY_GATE`

Suggested order:

1. Send the same non-binding questionnaire to Toyo Keizai, QUICK, J-Quants
   Pro/JPXI, and Bloomberg. No quote approval or trial at this step.
2. If none can answer the full contract, send it to LSEG, FactSet, and Nikkei
   NEEDS.
3. Build a field-by-field pass/fail crosswalk from written responses.
4. Ask for price only for packages that pass the critical field and license
   crosswalk.
5. Return for separate approval before any contract, trial, API connection,
   sample/raw-data acquisition, or U50/U100 execution.

## Gate controls

- New contract or subscription: none
- Quote requested or approved: none
- Provider API access: none
- Raw/sample data acquired: none
- U50/U100 backtest: not executed
- Formal Candidate promotion: none
- Real-money canary authorization: none
- Ver1.0 production changes: none
- Cloudflare, GitHub Actions production workflow, Google Sheets, Secrets,
  LINE, pending, and trading changes: none

The detailed evidence matrix and official URLs are in
`DATA_SOURCE_OPTIONS_MATRIX.md`; the machine-readable decision is in
`data_source_options_matrix.json`.
