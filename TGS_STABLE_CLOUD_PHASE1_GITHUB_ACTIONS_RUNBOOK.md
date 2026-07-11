# TGS Stable Cloud Paper Trading Ver1.0 Phase1 GitHub Actions Runbook

This runbook is for Phase1 only.

Phase1 scope:

- Daily Score Check only
- Google Sheets official ledger write
- Dashboard summary update
- No pending registration
- No LINE notification
- No broker API
- No real orders

## 1. Required GitHub Secrets

Repository:

```text
ai-stock-reporter
```

Open:

```text
Settings > Secrets and variables > Actions > New repository secret
```

Add these secrets:

| Secret | Required | Purpose |
|---|---:|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Yes | Full Google service account JSON. Do not paste it into chat. |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | Yes | Official TGS Cloud Paper Trading ledger spreadsheet ID. |
| `GOOGLE_DASHBOARD_SPREADSHEET_ID` | Recommended | TG AI Investment Lab Dashboard spreadsheet ID. |

Not required in Phase1:

| Secret | Reason |
|---|---|
| `LINE_CHANNEL_ACCESS_TOKEN` | Phase1 does not send LINE notifications. |

## 2. Service Account Sharing

Open the service account JSON locally and find:

```json
"client_email": "...@...iam.gserviceaccount.com"
```

Share both Google Sheets with this `client_email` as Editor:

1. `TGS Stable Ver1.0 Cloud Paper Trading Ledger`
   - Location: `Google Drive/TG AI Investment Lab/02_TGS/Stable_Ver1_0/Paper_Trading/`
   - Secret: `GOOGLE_SHEETS_SPREADSHEET_ID`

2. `TG AI Investment Lab Dashboard`
   - Location: `Google Drive/TG AI Investment Lab/00_Dashboard/`
   - Secret: `GOOGLE_DASHBOARD_SPREADSHEET_ID`

If the service account is not shared as Editor, GitHub Actions will fail with a Google Sheets permission error.

## 3. Workflow

File:

```text
.github/workflows/tgs-stable-cloud-paper.yml
```

Schedule:

```text
17 20 * * 1-5
timezone: Asia/Tokyo
```

This is 20:17 JST, Monday-Friday. The non-zero minute avoids the top-of-hour GitHub Actions queue peak.

The schedule is delayed from 18:05 JST because yfinance can lag shortly after the JP close. If data is still stale, the workflow records `data_stale` and does not treat the day as a formal `no_signal`.

Scheduled score dates use the latest scheduled cutoff at or before the actual score-check start time. For example, a Monday 20:17 run that starts Tuesday at 03:30 JST still uses Monday as `requested_as_of`. This is a weekday cutoff policy, not a JPX calendar: Japanese market holidays remain target dates and are expected to become `stale` when `data_date` differs.

Manual trigger:

```text
Actions > TGS Stable Cloud Paper Trading Ver1.0 > Run workflow
```

Inputs:

| Input | First run | Execute run |
|---|---|---|
| `as_of` | Required for score runs, e.g. `2026-07-03` | Required; use the same date |
| `dry_run` | `true` | `false` |
| `skip_dashboard` | `false` | `false` |

## 4. First Dry-Run

Run workflow with:

```text
as_of = latest trading date
dry_run = true
skip_dashboard = false
```

Expected:

- Action succeeds
- No Google Sheets write
- Artifact `tgs-stable-cloud-score-check` is uploaded
- Artifact contains:
  - `stable_daily_score_check_YYYY_MM_DD.csv`
  - `dashboard_tgs_preview.csv`
  - `dashboard_home_preview.csv`
  - `run_log_preview.csv`
  - `payload.json`

Check `payload.json`:

```json
"pending_registration_enabled": false
"real_trading_enabled": false
```

Check freshness fields:

```json
"requested_as_of": "YYYY-MM-DD"
"data_date": "YYYY-MM-DD"
"freshness_status": "current | stale | no_data"
```

If `freshness_status=stale`, expected Dashboard status is `data_stale`, not `no_signal`.

If `freshness_status=no_data`, expected Dashboard status is `data_unavailable`, not `no_signal`. Only `freshness_status=current` can produce a formal signal or formal `no_signal` result.

The Actions log and `payload.json` include `trigger_event`, `scheduled_cron`, `schedule_timezone`, `run_started_at_jst`, `requested_as_of`, `requested_as_of_source`, `schedule_resolution_policy`, `data_date`, and `freshness_status`. The scheduled source is `scheduled_cutoff` and its policy is `latest_prior_cutoff`.

## 5. Execute Run

After dry-run looks correct, run workflow again with:

```text
as_of = same latest trading date
dry_run = false
skip_dashboard = false
```

Expected Google Sheets writes:

- `TGS_Daily_Score_Check`
  - 15 rows inserted or updated for the target date
- `TGS_Run_Log`
  - 1 run row appended
- Dashboard `TGS`
  - 1 summary row inserted or updated
- Dashboard `Home`
  - 8 TGS rows inserted or updated
- Dashboard `Log`
  - 1 log row appended

Still not expected:

- `TGS_Pending` row creation
- `TGS_Positions` update
- `TGS_Trade_History` update
- LINE notification
- Any real trade/order action

## 6. Verify-Only Check

After execute, run locally or in a temporary GitHub Actions command:

```bash
GOOGLE_SERVICE_ACCOUNT_JSON='...' \
GOOGLE_SHEETS_SPREADSHEET_ID='...' \
GOOGLE_DASHBOARD_SPREADSHEET_ID='...' \
python stable_cloud_score_check.py --verify-only
```

Expected:

- `required_tabs_present = true`
- `latest_score_row_count = 15`
- `latest_run_log_row.status = success`
- Dashboard latest TGS/Home/Log values reflect the execute run

`--verify-only` reads existing Sheets state and does not score a date, so `as_of` is not required. `--init-only` also keeps its existing date-independent behavior. The workflow input remains optional at the UI schema level for these modes, while dry-run and execute score modes require an explicit manual `as_of`; an empty value fails in Python before market data or Sheets access.

## 7. Mac版との一致確認

For the same `as_of` date, compare:

- Cloud artifact: `stable_daily_score_check_YYYY_MM_DD.csv`
- Mac output: `stable_daily_score_check_YYYY_MM_DD.csv`

Required matching columns:

- `date`
- `ticker`
- `weekly_above_200ma`
- `weekly_macd_gc`
- `weekly_macd_uptrend`
- `daily_rsi_40_65`
- `daily_volume_1_5x`
- `stable_score`
- `signal_expected`
- `close`
- `daily_rsi`
- `volume_ratio`
- `data_latest_date`
- `data_status`
- `requested_as_of`
- `data_date`
- `freshness_status`

Acceptance:

```text
mismatch_count = 0
```

If the Mac version has not yet added the freshness columns, compare only the original score columns and separately confirm Cloud freshness fields.

## 8. Five-Trading-Day Parallel Monitoring

For 5 trading days:

- Keep Mac/ngrok configuration as backup.
- Run Cloud workflow daily.
- Confirm Cloud daily score rows are written.
- Confirm Dashboard summary is updated.
- Compare Cloud vs Mac score check.

After 5 consecutive successful trading days:

- Cloud becomes the primary Paper Trading infrastructure.
- Mac/ngrok becomes backup only.
- Phase2 can enable pending registration, still paper-only.

## 9. Safety Guardrails

Do not add or enable:

- Pending registration in Phase1
- LINE notification in Phase1
- Broker API
- Order placement
- Real trading
- Rule changes

Frozen values:

- Stable Score threshold: 90
- Universe: 15 tickers
- Stop loss: -10%
- Take profit: +30%
- Max holding: 60 trading days
