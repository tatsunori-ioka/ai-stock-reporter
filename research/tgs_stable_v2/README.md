# TGS Stable Ver2.0 Universe Lab

Independent, research-only reproduction of the frozen TGS Stable Ver1.0 rule.
Nothing in this directory connects to Google Sheets, Cloudflare, LINE, a
broker, or a production ledger.

## Reproduce

```bash
python3 -m pip install -r research/tgs_stable_v2/requirements.txt

PYTHONPATH=research/tgs_stable_v2/src \
python3 -m pytest research/tgs_stable_v2/tests -q

PYTHONPATH=research/tgs_stable_v2/src \
python3 research/tgs_stable_v2/run_u15.py
```

The raw public-price cache is ignored by Git. The committed data manifest
contains date coverage and deterministic hashes. Use `--refresh` to replace
the cache intentionally. Re-running from the same cache is byte-deterministic.
A fresh clone must re-download a mutable Yahoo snapshot; hashes expose drift,
but cannot reconstruct an older provider snapshot. A Formal Candidate would
need a legally archivable, versioned raw-data source.

Reported full-period portfolio return, drawdown, exposure and concurrency are
mechanical ex-post capacity-normalized diagnostics, not an investable capital
allocation. Split tables are closed independent-trade cohort summaries.

U50/U100 comparison is outside this gate and has no execution command.
