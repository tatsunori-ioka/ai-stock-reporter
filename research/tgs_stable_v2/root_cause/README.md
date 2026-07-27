# TGS Stable Ver2.0 root-cause diagnostic

Gate: `V2-R2B_ROOT_CAUSE_DIAGNOSTIC_AND_STOP_DECISION`

This directory contains a post-hoc, association-only diagnostic of the frozen
PIT-lite U15/U50/U100 experiment. It does not select a new universe, change a
score, threshold, exit, capacity, or priority rule, and it does not authorize
production use, a Formal Candidate, a purchase, or a real-money canary.

The diagnostic reads only the already licensed private run
`v2-r2a-20260727-d3b8ed0-integrity1`. Before loading analytical inputs it
validates the deletion manifest, every manifested file hash and size, directory
and file modes, and the three private bundle fingerprints recorded by PR #10.
It never reads raw API responses or request-cache bodies after the fingerprint
gate. It does not import an API client, read an API credential, or make a
network request.

Run from the repository root:

```bash
env -u JQUANTS_API_KEY \
  PYTHONDONTWRITEBYTECODE=1 \
  python3 research/tgs_stable_v2/root_cause/scripts/run_root_cause_diagnostic.py
```

The Git/GitHub fetch, push, and Draft-PR operations required by the surrounding
research gate are control-plane publication operations. They are not part of
the diagnostic runtime counters.

Repository outputs are aggregate-only. They exclude raw OHLCV, security codes,
complete membership lists, exact trade records, exact prices, and private file
bodies. Private cleanup remains `NOT_EXECUTED`.

The runner performs two complete same-cache executions and writes artifacts
only when their canonical aggregate bundle hashes match. Performance and
robustness calculations require signal, entry, and exit to be contained in the
same frozen split. Signal-cohort counts may include explicitly reported
cross-boundary or censored rows, but those rows do not enter quality metrics.

The output gate also parses every JSON/CSV artifact through the aggregate
schema validator and scans the research tree for credential-shaped values.
Both scan counts must be zero.

Current frozen result:

- diagnostic verdict: `NO_ACTIONABLE_DIAGNOSTIC_HYPOTHESIS`
- underperformance cause: `G_CLEAR_CAUSE_NOT_IDENTIFIED`
- Score monotonicity: `NOT_ESTABLISHED`
- Score 120: `INSUFFICIENT_SAMPLE_FOR_ROBUST_SCORE120_HYPOTHESIS`
- recommended final action: `END_TGS_STABLE_V2_RESEARCH`
- Formal Candidate: `HOLD`
- real-money canary: `none`

The final holdout was already observed before this diagnostic. It is not unused
out-of-sample evidence for any future rule. Findings are associations, not
causal proof, and no rule may be adopted from this gate.
