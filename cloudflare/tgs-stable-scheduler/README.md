# TGS Stable Cloudflare Scheduler

Stage 1 adds a Cloudflare Worker that can dispatch the existing TGS Stable
Cloud Phase1 workflow. It does not enable a production Cron Trigger.

## Production Contract

- Cron expression: `37 7 * * MON-FRI`
- Scheduled time: 07:37 UTC / 16:37 JST, Monday-Friday
- Score date source: `controller.scheduledTime` converted to `Asia/Tokyo`
- GitHub repository: `tatsunori-ioka/ai-stock-reporter`
- Workflow: `tgs-stable-cloud-paper.yml`
- Git ref: `main`
- Trigger origin: `cloudflare_cron`
- Secret binding name: `GITHUB_ACTIONS_TOKEN`

The Worker calls `controller.noRetry()`, validates the exact cron, and directly
awaits the GitHub dispatch. A non-200 GitHub response fails the Cron invocation.
Only `scheduled()` is exported; there is no public HTTP handler.

## Stage 1 State

`wrangler.jsonc` intentionally contains:

```json
"triggers": {
  "crons": []
}
```

The existing GitHub Actions `on.schedule` remains active. Do not add the
production Cloudflare Cron or deploy this Worker during Stage 1.

## Local Verification

```bash
pnpm install
pnpm typecheck
pnpm test
pnpm audit
```

Tests use a fake token and mocked GitHub responses. They do not access GitHub,
Google Sheets, LINE, a broker API, or any order path.

## Opt-In Dry-Run Smoke

Run only after the Stage 1 workflow changes exist on `main` and an authorized
token has been supplied outside source control:

```bash
printf 'GitHub token: '
IFS= read -rs GITHUB_ACTIONS_TOKEN
printf '\n'
export GITHUB_ACTIONS_TOKEN

pnpm smoke:dispatch --as-of 2026-07-14

unset GITHUB_ACTIONS_TOKEN
```

The smoke command accepts only `--as-of YYYY-MM-DD`. Its request is fixed to:

- `ref=main`
- `dry_run=true`
- `skip_dashboard=true`
- `trigger_origin=cloudflare_cron`
- `dispatch_key=cloudflare_cron:<as_of>T07:37:00.000Z`

There is no smoke command option that can enable execute mode or Dashboard
writes. The token is read from `GITHUB_ACTIONS_TOKEN` and is never included in
the payload, audit log, or surfaced exception.

## Stage 2

After the dry-run smoke succeeds, use a separate change to remove GitHub
`on.schedule` and set the production Cloudflare Cron to
`37 7 * * MON-FRI`. Confirm that no GitHub scheduled run is queued before the
Cloudflare trigger is enabled.
