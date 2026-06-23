# TGS Stable Ver1.0 Paper Trading Automation

This automation is record-only. It never sends real buy or sell orders.

## Production Split

Render Free does not support Persistent Disks, so Render is not used as the official paper-trading ledger.

Render remains responsible for:

- TradingView webhook receive
- Stable Ver1.0 validation
- LINE notification

Mac is responsible for the official paper-trading ledger:

- pending orders
- positions
- trade history
- account
- daily log

## Fixed Rule

- Stable Score >= 90
- Large cap
- Strong sector
- Entry assumption: next trading day open after accepted signal
- Stop loss: -10%
- Take profit: +30%
- Max holding: 60 trading days

The rule is frozen. Do not change it in paper-trading automation.

## Mac Ledger Directory

Official local ledger:

```text
/Users/iokatatsunori/Documents/Codex/tgs_stable_paper_ledger
```

CSV files:

- `stable_paper_pending_orders.csv`
- `stable_paper_positions.csv`
- `stable_paper_trade_history.csv`
- `stable_paper_account.csv`
- `stable_paper_daily_log.csv`
- `stable_paper_daily_YYYY-MM-DD.csv`
- `launchd.out`
- `launchd.err`

## Add LINE Signal To Pending

When LINE sends a Stable signal, add it to the Mac ledger.

Minimum command:

```bash
cd /Users/iokatatsunori/Documents/Codex/2026-06-22/tgs-growth-project-tgs-stable-15/work/ai-stock-reporter
STABLE_DATA_DIR=/Users/iokatatsunori/Documents/Codex/tgs_stable_paper_ledger \
python3 stable_add_pending.py --ticker 8058.T --signal-date 2026-06-24
```

With optional values from LINE:

```bash
STABLE_DATA_DIR=/Users/iokatatsunori/Documents/Codex/tgs_stable_paper_ledger \
python3 stable_add_pending.py \
  --ticker 8058.T \
  --signal-date 2026-06-24 \
  --score 120 \
  --daily-rsi 55 \
  --volume-ratio 2.0
```

This only creates a pending paper order. No real order is sent.

## Manual Daily Run

```bash
cd /Users/iokatatsunori/Documents/Codex/2026-06-22/tgs-growth-project-tgs-stable-15/work/ai-stock-reporter
STABLE_DATA_DIR=/Users/iokatatsunori/Documents/Codex/tgs_stable_paper_ledger \
python3 stable_paper_daily.py
```

## Automatic Daily Run

LaunchAgent file:

```text
com.tgs.stable.paper.daily.plist
```

Schedule:

- Monday to Friday
- 18:10 JST

Install:

```bash
mkdir -p ~/Library/LaunchAgents
cp /Users/iokatatsunori/Documents/Codex/2026-06-22/tgs-growth-project-tgs-stable-15/work/ai-stock-reporter/com.tgs.stable.paper.daily.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.tgs.stable.paper.daily.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.tgs.stable.paper.daily.plist
```

Check:

```bash
launchctl list | grep com.tgs.stable.paper.daily
cat /Users/iokatatsunori/Documents/Codex/tgs_stable_paper_ledger/launchd.out
cat /Users/iokatatsunori/Documents/Codex/tgs_stable_paper_ledger/launchd.err
```

Holiday note:

`launchd` runs Monday to Friday. Japanese market holidays may still run, but if there is no valid market data the job keeps positions/pending safely unchanged.

## Render Is Not Official Ledger

Render Free may write temporary CSVs to `outputs`, but those files are not durable.

Do not treat Render CSVs as the official paper-trading ledger unless the service is upgraded and a Persistent Disk is mounted.

If Render is upgraded later:

```text
Persistent Disk Mount Path = /data
```

Only then can Render become the official ledger.

## TradingView Watchlist

Generated file:

```text
tradingview_stable_watchlist.csv
```

Regenerate:

```bash
python3 generate_stable_watchlist.py
```
