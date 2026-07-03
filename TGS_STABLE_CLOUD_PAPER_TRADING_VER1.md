# TGS Stable Cloud Paper Trading Ver1.0

Phase 1 implements cloud daily score checks only.

This is paper-trading infrastructure. It never sends real buy or sell orders.

## Frozen Stable Ver1.0 Rules

Do not change these values:

- Universe: 15 TGS Stable Ver1.0 tickers
- Stable Score threshold: 90
- Stop loss: -10%
- Take profit: +30%
- Max holding: 60 trading days
- Paper Trading only
- Real trading: disabled

Phase 1 does not create pending orders. Pending registration starts only after the cloud score check has been stable for 5 trading days.

## Official Cloud Ledger

Create a Google Sheets spreadsheet under:

```text
Google Drive/TG AI Investment Lab/02_TGS/Stable_Ver1_0/Paper_Trading/
```

Suggested spreadsheet name:

```text
TGS Stable Ver1.0 Cloud Paper Trading Ledger
```

The script initializes these tabs:

- `TGS_Pending`
- `TGS_Positions`
- `TGS_Trade_History`
- `TGS_Account`
- `TGS_Daily_Log`
- `TGS_Daily_Score_Check`
- `TGS_Run_Log`

Dashboard summary is written separately to the existing TG AI Investment Lab Dashboard spreadsheet. Dashboard tabs are display-only summaries, not the official ledger.

## GitHub Secrets

Required for Phase 1:

- `GOOGLE_SERVICE_ACCOUNT_JSON`
  - Full service account JSON.
  - The service account must have edit access to the official ledger spreadsheet.
  - If Dashboard sync is enabled, it also needs edit access to the Dashboard spreadsheet.

- `GOOGLE_SHEETS_SPREADSHEET_ID`
  - Spreadsheet ID of `TGS Stable Ver1.0 Cloud Paper Trading Ledger`.

Optional for Dashboard sync:

- `GOOGLE_DASHBOARD_SPREADSHEET_ID`
  - Spreadsheet ID of `TG AI Investment Lab Dashboard`.
  - If missing, Phase 1 still writes the official ledger and skips Dashboard update.

Not required in Phase 1:

- `LINE_CHANNEL_ACCESS_TOKEN`
  - No LINE notification is sent by `stable_cloud_score_check.py` in Phase 1.
  - LINE notification will be reintroduced when pending registration is enabled in a later phase.

## Workflow

File:

```text
.github/workflows/tgs-stable-cloud-paper.yml
```

Schedule:

```text
5 9 * * 1-5
```

GitHub Actions cron uses UTC, so this is 18:05 JST Monday-Friday.

Manual run:

- `workflow_dispatch`
- `dry_run=true` means no Google Sheets write.
- `dry_run=false` writes to Google Sheets.
- `as_of` can be set to a date such as `2026-07-03`.

## Local Commands

Dry-run:

```bash
python stable_cloud_score_check.py --as-of 2026-07-03
```

Initialize official ledger tabs:

```bash
GOOGLE_SHEETS_SPREADSHEET_ID="..." \
GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account", ...}' \
python stable_cloud_score_check.py --init-only --execute
```

Execute score check and write official ledger:

```bash
GOOGLE_SHEETS_SPREADSHEET_ID="..." \
GOOGLE_DASHBOARD_SPREADSHEET_ID="..." \
GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account", ...}' \
python stable_cloud_score_check.py --as-of 2026-07-03 --execute
```

Verify Google Sheets state without writing:

```bash
GOOGLE_SHEETS_SPREADSHEET_ID="..." \
GOOGLE_DASHBOARD_SPREADSHEET_ID="..." \
GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account", ...}' \
python stable_cloud_score_check.py --verify-only
```

## Output

Dry-run artifacts:

```text
outputs/cloud_score_check/
```

Google Sheets writes in Phase 1:

- Upsert 15 score rows into `TGS_Daily_Score_Check`
- Append one run row into `TGS_Run_Log`
- If Dashboard ID is configured:
  - Upsert one row into `TGS`
  - Upsert seven rows into `Home`
  - Append one row into `Log`

## Safety Boundaries

- No pending registration in Phase 1.
- No position updates in Phase 1.
- No trade history writes in Phase 1.
- No account updates in Phase 1.
- No broker API.
- No real orders.
- Mac/ngrok remains as backup until cloud mode is stable for 5 trading days.

## Phase1 GitHub Actions Runbook

Detailed dry-run, execute, and verification steps:

```text
TGS_STABLE_CLOUD_PHASE1_GITHUB_ACTIONS_RUNBOOK.md
```
