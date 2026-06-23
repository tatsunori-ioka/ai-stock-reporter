# TGS Stable Ver1.0 Paper Trading Automation

This automation is record-only. It never sends real buy or sell orders.

## Fixed Rule

- Stable Score >= 90
- Large cap
- Strong sector
- Stop loss: -10%
- Take profit: +30%
- Max holding: 60 trading days
- Entry assumption: next trading day open after an accepted webhook signal

## Files

Default data directory:

- Render with persistent disk: `/data`
- Fallback/local: `outputs`

CSV files:

- `stable_paper_pending_orders.csv`
- `stable_paper_positions.csv`
- `stable_paper_trade_history.csv`
- `stable_paper_account.csv`
- `stable_paper_daily_log.csv`
- `stable_paper_daily_YYYY-MM-DD.csv`

## Render Option

Recommended only if the Render service has a persistent disk mounted at `/data`.
Without a persistent disk, CSV state can be lost when the service restarts.

Endpoint:

```text
POST /tasks/stable-paper-daily
```

Required security:

```text
STABLE_TASK_TOKEN=<long random token>
```

Call the endpoint with:

```bash
curl -X POST "https://ai-stock-reporter.onrender.com/tasks/stable-paper-daily" \
  -H "Content-Type: application/json" \
  -H "X-Stable-Task-Token: <STABLE_TASK_TOKEN>" \
  -d '{}'
```

Schedule:

- Use Render Cron Job if available, or cron-job.org.
- Time: every Tokyo business day at 18:10 JST.
- HTTP method: POST.

## Mac Option

Safer if there is no Render persistent disk. The CSV ledger stays on the Mac.

Manual run:

```bash
cd /Users/iokatatsunori/Documents/Codex/2026-06-22/tgs-growth-project-tgs-stable-15/work/ai-stock-reporter
python3 stable_paper_daily.py
```

LaunchAgent schedule example:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.tgs.stable.paper.daily</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/Users/iokatatsunori/Documents/Codex/2026-06-22/tgs-growth-project-tgs-stable-15/work/ai-stock-reporter/stable_paper_daily.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/iokatatsunori/Documents/Codex/2026-06-22/tgs-growth-project-tgs-stable-15/work/ai-stock-reporter</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>18</integer>
    <key>Minute</key>
    <integer>10</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/tmp/tgs_stable_paper_daily.out</string>
  <key>StandardErrorPath</key>
  <string>/tmp/tgs_stable_paper_daily.err</string>
</dict>
</plist>
```

Install:

```bash
mkdir -p ~/Library/LaunchAgents
cp com.tgs.stable.paper.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.tgs.stable.paper.daily.plist
```

## Render vs Mac

Render advantages:

- Runs even when the Mac is off.
- Same environment as webhook.
- Best if `/data` persistent disk is enabled.

Render risks:

- CSV state is unsafe without persistent disk.
- Free instances can sleep.
- Requires an external scheduler or Render Cron Job.

Mac advantages:

- CSV files are easy to inspect and back up.
- No persistent disk issue.
- Simple `launchd` schedule.

Mac risks:

- Does not run if the Mac is off or asleep.
- Needs local Python/yfinance setup.

Recommendation:

- Use Render if `/data` persistent disk is enabled.
- Otherwise use Mac `launchd` until the ledger is moved to a database.

## TradingView Watchlist

Generate:

```bash
python3 generate_stable_watchlist.py
```

Output:

```text
tradingview_stable_watchlist.csv
```
