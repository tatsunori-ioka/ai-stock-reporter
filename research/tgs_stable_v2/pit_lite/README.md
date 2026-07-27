# TGS Stable Ver2.0 — V2-R2A PIT-lite Universe Comparison

This directory is an isolated, research-only implementation of the explicitly
approved PIT-lite U15/U50/U100 comparison. It does not change or authorize the
Formal U50/U100 design, a Formal Candidate, production, or a real-money canary.

The immutable rules are in
[`contracts/PIT_LITE_RESEARCH_CONTRACT.json`](contracts/PIT_LITE_RESEARCH_CONTRACT.json).
Licensed or reconstructible J-Quants material is kept only in the FileVault
protected private root recorded there. Repository results are aggregate-only.

Workflow:

1. `scripts/acquire_jquants_pit_lite.py --estimate` performs a zero-network
   estimate and preflight description.
2. `scripts/acquire_jquants_pit_lite.py --live --run-id ...` verifies FileVault,
   private permissions, and the environment-held key before bounded GET-only
   acquisition. It is single-threaded, journals every attempt before dispatch,
   and stops before attempt 3,001. If an earlier aborted run consumed attempts,
   `--prior-attempts N` subtracts them from the new-run hard limit and binds the
   value into the checkpoint.
3. `scripts/run_pit_lite_comparison.py --run-id ...` reads the private cache,
   writes the private exact ledger, and publishes only the approved aggregate
   report/results.
4. `scripts/cleanup_private_data.py` is dry-run by default. Cleanup is not
   authorized in V2-R2A and must not be executed for the live run.

No command accepts a credential as an argument. The API key is read only from
`JQUANTS_API_KEY` and is never printed or persisted.
