# TGS Stable Cloudflare Scheduler

Stage 2b cuts the Phase1 production schedule over to Cloudflare. The formal
automatic start time is 16:37 JST, Monday-Friday, and Cloudflare is the only
automatic trigger.

## Adoption Evidence

The 2026-07-16 shadow observations both completed successfully with
`requested_as_of=2026-07-16`, `data_date=2026-07-16`,
`freshness_status=current`, and 15 scored rows:

- 16:37 JST: GitHub run `29480526880`
- 17:07 JST: GitHub run `29482298471`

Because both observations were current, the earlier 16:37 JST time was adopted.

## Production Contract

- Cron expression: `37 7 * * MON-FRI` (07:37 UTC / 16:37 JST)
- Score date source: `controller.scheduledTime` converted to `Asia/Tokyo`
- GitHub repository: `tatsunori-ioka/ai-stock-reporter`
- Workflow: `tgs-stable-cloud-paper.yml`
- Git ref: `main`
- Trigger origin: `cloudflare_cron`
- Dispatch key: `cloudflare_cron:<ISO scheduledTime>`
- Secret binding name: `GITHUB_ACTIONS_TOKEN`
- Public HTTP endpoint: disabled with `workers_dev=false`

The scheduled handler is hard-coded to `dry_run=false` and
`skip_dashboard=false`. Neither setting, environment binding, nor handler input
can switch the scheduled path back to dry-run or suppress the Dashboard update.
The Worker calls `controller.noRetry()`, validates the exact Cron, directly
awaits the GitHub dispatch, and fails the Cron invocation when GitHub fails.

Only `scheduled()` is exported. There is no public HTTP handler or
`workers.dev` route.

## GitHub Actions

The GitHub Actions `on.schedule` trigger is removed. `workflow_dispatch`
remains available for manual dry-run and execute operations, while the existing
run-context handling for `manual_ui`, `cloudflare_cron`, `dispatch_key`, and
`external_scheduler` remains unchanged. Cloudflare is the only automatic
invocation source. The existing Cloud Python `init-only` and `verify-only`
paths are also unchanged.

## Phase1 Write Scope

Stage 2b is a Phase1 execute run. It preserves the existing freshness guard,
score calculation, signal conditions, Google Sheets columns, and update logic.
Execute writes only the established Phase1 outputs:

- `TGS_Daily_Score_Check`
- `TGS_Run_Log`
- Dashboard

Pending registration, Cloud LINE notifications, position registration, trade
history, account updates, daily-log updates, trading, broker APIs, order
processing, and fill processing remain disabled. In particular,
`pending_registration_enabled=false` and `real_trading_enabled=false` remain
part of the run result.

## Diagnostic Smoke

The diagnostic smoke command remains independently fixed to `dry_run=true`,
`skip_dashboard=true`, `ref=main`, and `trigger_origin=cloudflare_cron`. It has
no option or environment setting that can enable execute mode.

```bash
printf 'GitHub token: '
IFS= read -rs GITHUB_ACTIONS_TOKEN
printf '\n'
export GITHUB_ACTIONS_TOKEN

pnpm smoke:dispatch --as-of 2026-07-16

unset GITHUB_ACTIONS_TOKEN
```

## Local Verification

```bash
pnpm install --frozen-lockfile
pnpm typecheck
pnpm test
pnpm audit
pnpm wrangler deploy --dry-run
```

Tests use a fake token and mocked GitHub responses. They do not access GitHub,
Google Sheets, LINE, a broker API, or any order path.

## Rollback

The Stage 2a rollback target is:

- Deployment ID: `f9ab6f93-82fb-45ce-8a8d-8cee253e91a7`
- Worker version: `29ce3bb3-9ff3-44e2-8f4f-13a5ead9a4f7`

Rollback order:

1. Run `pnpm wrangler rollback 29ce3bb3-9ff3-44e2-8f4f-13a5ead9a4f7 --name tgs-stable-scheduler --yes`.
2. Restore the Stage 2a dry-run Cron pair, or apply `crons=[]` to stop Cloudflare scheduling.
3. Merge a rollback PR that restores the prior GitHub `on.schedule` definition.
4. Before restoring any automatic trigger, check whether that date already has a successful execute run and do not duplicate it.

Worker version rollback does not restore Cron Triggers or the GitHub workflow;
those two control planes must be restored explicitly.
