# License and deletion boundary

This record summarizes the previously documented J-Quants support
clarification. It does not reproduce correspondence or personal information.

- While Premium remains active, legitimately obtained data may be stored in an
  encrypted local environment for private analysis, with acquisition date and
  conditions.
- Non-reconstructible aggregates such as CAGR, drawdown, win rate, profit
  factor, counts, periods, missing counts, SHA-256 values, methods and code may
  be retained. Repeated provision of J-Quants-derived analysis to third parties
  is outside the private-use boundary.
- A downgrade to Standard requires deletion of data outside the new plan,
  including copies and backups, and ends the right to use it.
- At the end of the paid period or withdrawal, raw, reconstructible processed
  data, copies and backups must all be deleted. Non-raw aggregates, hashes,
  methods and code are outside that deletion set.

The live run therefore stores raw responses, normalized bars, annual
membership, exact trades and checkpoints only beneath:

`/Users/iokatatsunori/Library/Application Support/TGSStableV2/JQuantsPITLite`

FileVault and mode `0700`/`0600` are mandatory. Nothing in those private
categories may be committed. The cleanup utility is installed and tested only
with synthetic temporary data in this gate. Actual cleanup remains
`NOT_EXECUTED`; Premium is maintained through completion of the approved
exploration.
