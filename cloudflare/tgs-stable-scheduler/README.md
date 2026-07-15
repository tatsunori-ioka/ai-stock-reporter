# TGS Stable Cloudflare Scheduler

Stage 2a is a dry-run-only shadow observation. It automatically compares the
same-day market-data state at 16:37 JST and 17:07 JST without writing Google
Sheets or the Dashboard.

## Shadow Observation Contract

- Cron expressions:
  - `37 7 * * MON-FRI` (07:37 UTC / 16:37 JST)
  - `7 8 * * MON-FRI` (08:07 UTC / 17:07 JST)
- Score date source: `controller.scheduledTime` converted to `Asia/Tokyo`
- GitHub repository: `tatsunori-ioka/ai-stock-reporter`
- Workflow: `tgs-stable-cloud-paper.yml`
- Git ref: `main`
- Trigger origin: `cloudflare_cron`
- Secret binding name: `GITHUB_ACTIONS_TOKEN`

The scheduled handler is hard-coded to `dry_run=true` and
`skip_dashboard=true`. There is no setting, environment binding, or handler
input that can switch Stage 2a to execute mode. The dispatch key is
`cloudflare_cron:<ISO scheduledTime>`.

The Worker calls `controller.noRetry()`, accepts exactly the two Cron
expressions above, and directly awaits the GitHub dispatch. A non-200 GitHub
response fails the Cron invocation. Only `scheduled()` is exported; there is no
public HTTP handler.

## Stage 2a State

`wrangler.jsonc` defines the two shadow-observation Cron Triggers. This change
does not deploy the Worker, register the production Secret, or activate either
Cron in Cloudflare. Those operations require a separate deployment gate.

The existing GitHub Actions `on.schedule` remains enabled throughout Stage 2a.
The two Cloudflare observations are dry runs, so they do not write
`TGS_Run_Log`, `TGS_Daily_Score_Check`, the Dashboard, or any pending, position,
trade-history, account, or daily-log tab.

After one business day of 16:37 and 17:07 results has been reviewed, select the
initial production time. Enabling a formal execute path and coordinating the
removal of the existing GitHub schedule belong to a separate Stage 2b PR.

## Local Verification

```bash
pnpm install
pnpm typecheck
pnpm test
pnpm audit
pnpm wrangler deploy --dry-run
```

Tests use a fake token and mocked GitHub responses. They do not access GitHub,
Google Sheets, LINE, a broker API, or any order path.

## Opt-In Dry-Run Smoke

The diagnostic smoke command is also dry-run-only. Run it only with an
authorized repository-scoped token supplied outside source control:

```bash
printf 'GitHub token: '
IFS= read -rs GITHUB_ACTIONS_TOKEN
printf '\n'
export GITHUB_ACTIONS_TOKEN

pnpm smoke:dispatch --as-of 2026-07-16

unset GITHUB_ACTIONS_TOKEN
```

The smoke command accepts only `--as-of YYYY-MM-DD`. Its request is fixed to:

- `ref=main`
- `dry_run=true`
- `skip_dashboard=true`
- `trigger_origin=cloudflare_cron`
- `dispatch_key=cloudflare_cron:<as_of>T07:37:00.000Z`

The token is never included in the payload, audit log, or surfaced exception.
