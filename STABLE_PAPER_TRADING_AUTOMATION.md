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

Headquarters storage standard from 2026-06-25:

```text
Google Drive/TG AI Investment Lab/02_TGS/Stable_Ver1_0/Paper_Trading/
```

Dashboard copies only:

```text
Google Drive/TG AI Investment Lab/00_Dashboard/Stable_Ver1_0/
```

The dashboard folder must not be treated as the official ledger.

Official local ledger:

```text
/Users/iokatatsunori/Library/Application Support/TGSStablePaper/ledger
```

Current note: Codex could not see a mounted Google Drive folder on 2026-06-25. Keep this local ledger active until the mounted Google Drive path is confirmed, then update launchd `STABLE_DATA_DIR` to the headquarters standard folder.

CSV files:

- `stable_paper_pending_orders.csv`
- `stable_paper_positions.csv`
- `stable_paper_trade_history.csv`
- `stable_paper_account.csv`
- `stable_paper_daily_log.csv`
- `stable_paper_daily_YYYY-MM-DD.csv`
- `launchd.out`
- `launchd.err`
- `pending_server.out`
- `pending_server.err`

Runtime app directory:

```text
/Users/iokatatsunori/Library/Application Support/TGSStablePaper/app
```

## Automatic Pending Registration

When Render accepts a Stable Ver1.0 signal, it can forward the accepted signal to the Mac local pending server.

Mac local endpoint:

```text
http://127.0.0.1:8765/stable/pending
```

Local pending server:

```text
com.tgs.stable.pending.server.plist
```

The server only appends to `stable_paper_pending_orders.csv`. It never sends buy or sell orders.

Render cannot reach `127.0.0.1` on your Mac directly. Use a secure tunnel such as ngrok, Cloudflare Tunnel, or Tailscale Funnel, then set these Render environment variables:

```text
STABLE_MAC_PENDING_WEBHOOK_URL=https://YOUR_TUNNEL_DOMAIN/stable/pending
STABLE_MAC_PENDING_WEBHOOK_TOKEN=<same token as local_pending.env>
```

Local token file:

```text
/Users/iokatatsunori/Library/Application Support/TGSStablePaper/local_pending.env
```

Do not paste this token into chat.

After setup, a valid Render webhook response should include:

```json
{
  "accepted": true,
  "mac_pending_sent": true
}
```

## Manual Pending Fallback

Manual add is only a fallback when the tunnel or Mac server is unavailable.

Minimum command:

```bash
cd "/Users/iokatatsunori/Library/Application Support/TGSStablePaper/app"
STABLE_DATA_DIR="/Users/iokatatsunori/Library/Application Support/TGSStablePaper/ledger" \
python3 stable_add_pending.py --ticker 8058.T --signal-date 2026-06-24
```

With optional values from LINE:

```bash
STABLE_DATA_DIR="/Users/iokatatsunori/Library/Application Support/TGSStablePaper/ledger" \
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
cd "/Users/iokatatsunori/Library/Application Support/TGSStablePaper/app"
STABLE_DATA_DIR="/Users/iokatatsunori/Library/Application Support/TGSStablePaper/ledger" \
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
cp "/Users/iokatatsunori/Library/Application Support/TGSStablePaper/app/com.tgs.stable.paper.daily.plist" ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.tgs.stable.paper.daily.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.tgs.stable.paper.daily.plist
```

Check:

```bash
launchctl list | grep com.tgs.stable.paper.daily
cat "/Users/iokatatsunori/Library/Application Support/TGSStablePaper/ledger/launchd.out"
cat "/Users/iokatatsunori/Library/Application Support/TGSStablePaper/ledger/launchd.err"
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
