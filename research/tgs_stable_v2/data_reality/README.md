# V2-R1B Data & Portfolio Reality Gate

This directory is an isolated, research-only audit of the personal J-Quants
Premium API V2. It does not run U50/U100, alter the frozen U15 result, import
production code, or connect to Cloudflare, GitHub Actions production
workflows, Google Sheets, LINE, a broker, pending ledgers, or order handling.

## Gate result

- Capability verdict: `PRO_OR_ALTERNATIVE_REQUIRED`
- Formal U50/U100 possible: `false`
- Formal U50/U100 authorized: `false`
- U50/U100 backtest executed: `false`
- Premium: maintain pending an approved source/archival gate and written
  support clarification
- Standard downgrade: do not downgrade yet
- U15 split/reverse-split-adjusted rerun: technically possible on a common
  period beginning no earlier than the provider's `2008-05-07` coverage, but
  comprehensive corporate-action coverage is not established and execution is
  not authorized here; the full frozen U15 period beginning in 2004 is
  unavailable

Personal Premium passed the bounded checks for historical active-issue
snapshots, historical market/sector codes, and daily raw/adjusted fields. Three
official split/reverse-split factors matched and passed continuity checks, but
the broader corporate-action factor capability remains `PARTIAL`. One
later-delisted issue was verified, but that single example is only `PARTIAL`
evidence for population-wide inclusion.
`ProdCat` was observed but is also `PARTIAL` because a domestic-stock category
does not by itself prove ordinary/common share class. The service did not
directly provide dated listing/delisting intervals, trading unit, ticker
lineage or a stable security ID, dated corporate-group mapping, or sufficient
dated special-treatment/untradeable status. Long-term reproducible raw
snapshot retention also requires written support clarification.

See:

- `reports/JQUANTS_PREMIUM_CAPABILITY_AUDIT.md`
- `docs/DATA_SOURCE_DECISION.md`
- `results/jquants_probe_summary.json`
- `results/jquants_capability_matrix.json`

## Probe safety contract

`scripts/probe_jquants_v2.py` has these hard boundaries:

- default invocation is a zero-network, zero-credential-read, zero-file-write
  dry run;
- live mode requires an explicit `--live` flag and explicit audit date;
- only HTTPS GET requests to
  `api.jquants.com/v2/equities/master` and
  `api.jquants.com/v2/equities/bars/daily` are allowed;
- every HTTP attempt is counted before dispatch, with a ceiling of 30 per
  process and `--prior-attempts` carrying the audit total across restarted
  processes;
- there are no hidden retries, concurrency, bulk CSV calls, or full-market
  full-history calls;
- the API key is read only from `JQUANTS_API_KEY`, sent only in `x-api-key`,
  and never written or printed;
- full response bodies are written only to a random directory below `/tmp`,
  parsed, hashed, summarized, and deleted on exit;
- generated JSON is restricted to this directory's `results/` folder.

The recorded audit used 10 attempts: one TLS attempt failed before an HTTP
response under the initial local CA configuration, followed by nine successful
HTTP 200 calls after retaining certificate verification and selecting the
system CA bundle. No retry was hidden, and no raw response was retained.

## Commands

Dry run:

```bash
python3 research/tgs_stable_v2/data_reality/scripts/probe_jquants_v2.py
```

Contract tests:

```bash
PYTHONDONTWRITEBYTECODE=1 \
python3 -m pytest \
  research/tgs_stable_v2/data_reality/tests/test_probe_contract.py \
  -q -p no:cacheprovider
```

For a separately approved live rerun, provide the key through a hidden shell
prompt without saving it to a file:

```bash
read -s "JQUANTS_API_KEY?J-Quants API key: "
export JQUANTS_API_KEY

python3 research/tgs_stable_v2/data_reality/scripts/probe_jquants_v2.py \
  --live \
  --audit-as-of YYYY-MM-DD \
  --prior-attempts 0 \
  --base-commit 52ead3fe27c67da60d8eede4bc38fd1b4311f8ce

unset JQUANTS_API_KEY
```

A live rerun intentionally replaces the two sanitized generated artifacts and
must occur only on an approved research branch. Provider responses can change,
so hashes are audit evidence, not a promise that a future query reproduces the
same bytes. After any failed or interrupted run, do not restart with zero:
pass the cumulative attempts already spent, for example
`--prior-attempts 10`.

## Licensed-data boundary

The repository contains no API response body, full issue list, OHLCV series,
credential, `.env`, or authentication material. The one delisted code and
three corporate-action codes are bounded probe parameters backed by public
JPX notices; no company-name or raw-price values are stored.

Personal J-Quants is an own-use service. Raw internet distribution is not
permitted. The terms require Data and duplicates to be deleted after specified
subscription-cancellation and membership-cancellation paths. Ephemeral
processing is limited to noncommercial, nonacademic personal own use.
Persistent versioned local storage is not given an explicit safe harbor and is
`SUPPORT_CONFIRMATION_REQUIRED_WITH_CANCELLATION_DELETION_DUTY`.

Whether public aggregate/hash artifacts fall on the permitted-analysis side or
the prohibited edited/processed-Data side is also not stated as a general safe
harbor. This one-time audit stores only the bounded metadata expressly allowed
by the research gate; that scope is not a legal conclusion or permission for
future/continuing publication. The personal terms were last updated
2026-01-19; Article 1 makes the terms prevail over inconsistent FAQ material,
and Article 24 makes the Japanese text authoritative.
