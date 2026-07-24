# TGS Stable Ver1.0 Cloud Phase1 5営業日安定確認

## 正式判定方針

Cloud Phase1の正式判定は Cloud Python正本 + Google Sheets正式台帳で行う。

正式シグナル条件:

- `freshness_status = current`
- `stable_score >= 90`
- `signal_expected = true`

TradingView / LINE通知は参考通知扱いとする。

Cloud Phase1では次の機能を有効化しない。

- pending登録
- Cloud LINE通知
- 売買処理
- 証券API
- 注文処理
- 約定処理

## Cloudflare版 無人5営業日結果

対象期間:

- Day 1: 2026-07-17
- Day 2: 2026-07-21
- Day 3: 2026-07-22
- Day 4: 2026-07-23
- Day 5: 2026-07-24

2026-07-20は海の日による市場休業日のためHOLD・非カウントとする。

| Day | Date | 判定 | GitHub run ID | Cloud Python run_id | timestamp | requested_as_of | data_date | freshness_status | rows_scored | signal_count | max_score_ticker | max_score | 正式シグナル |
|---:|---|---|---:|---|---|---|---|---|---:|---:|---|---:|---|
| Day 1 | 2026-07-17 | OK | 29563655123 | tgs-stable-cloud-score-check-20260717T163731 | 2026-07-17 16:37:31 | 2026-07-17 | 2026-07-17 | current | 15 | 0 | 6367.T | 70 | なし |
| Day 2 | 2026-07-21 | OK | 29811168980 | tgs-stable-cloud-score-check-20260721T163824 | 2026-07-21 16:38:24 | 2026-07-21 | 2026-07-21 | current | 15 | 0 | 6367.T | 70 | なし |
| Day 3 | 2026-07-22 | OK | 29900913947 | tgs-stable-cloud-score-check-20260722T163834 | 2026-07-22 16:38:34 | 2026-07-22 | 2026-07-22 | current | 15 | 0 | 6367.T | 70 | なし |
| Day 4 | 2026-07-23 | OK | 29988804868 | tgs-stable-cloud-score-check-20260723T163827 | 2026-07-23 16:38:27 | 2026-07-23 | 2026-07-23 | current | 15 | 0 | 6367.T | 70 | なし |
| Day 5 | 2026-07-24 | OK | 30076109305 | tgs-stable-cloud-score-check-20260724T163824 | 2026-07-24 16:38:24 | 2026-07-24 | 2026-07-24 | current | 15 | 0 | 6367.T | 70 | なし |

各runは次の条件を満たした。

- GitHub Actions: `event=workflow_dispatch`
- branch: `main`
- trigger_origin: `cloudflare_cron`
- mode: `execute`
- dispatch_key: 対象日の07:37 UTC
- conclusion: `success`
- requested_as_of_source: `external_scheduler`
- pending_registration_enabled: `false`
- real_trading_enabled: `false`

## Google Sheets正式台帳

読み取り確認結果:

- `TGS_Run_Log`: 対象run_idごとに1行、計5行
- `TGS_Daily_Score_Check`: 各日15行、計75行
- `TGS_Pending`: ヘッダーのみ
- `TGS_Positions`: ヘッダーのみ
- `TGS_Trade_History`: ヘッダーのみ
- `TGS_Account`: ヘッダーのみ
- `TGS_Daily_Log`: ヘッダーのみ
- Cloud LINE通知処理: なし
- pending処理: なし
- 売買・証券API・注文・約定処理: なし

## 市場休業日 run

| Date | 判定 | GitHub run ID | Cloud Python run_id | timestamp | requested_as_of | data_date | freshness_status | rows_scored | signal_count | 扱い |
|---|---|---:|---|---|---|---|---|---:|---:|---|
| 2026-07-20 | HOLD | 29725221536 | tgs-stable-cloud-score-check-20260720T163821 | 2026-07-20 16:38:21 | 2026-07-20 | 2026-07-17 | stale | 15 | 0 | 市場休業日 / 非カウント |

このrunは市場休業日のschedule targetをそのままrequested_as_ofとし、前営業日のdata_dateと一致しないためstaleとなった。JPX営業日へ自動補正せず、freshness guardが機能した証跡として保持する。

## 総合判定

2026-07-24時点:

- Day 1: OK
- Day 2: OK
- Day 3: OK
- Day 4: OK
- Day 5: OK
- 5営業日安定確認: **5 / 5 OK**
- 5日間のsignal_count: すべて0
- 正式シグナル: なし
- 少額手動カナリア運用: **進行可**

少額手動カナリアの対象は、2026-07-27以降に新規発生する最初の正式シグナルとする。過去シグナルを遡って売買しない。

5営業日安定確認の完了は、自動pending登録、Cloud LINE通知、自動売買、証券API連携または注文処理の有効化を承認するものではない。

## 移行前確認ログ

Cloudflare正式切替前に確認したcurrent runを履歴として保持する。

| Date | run_id | timestamp | as_of | data_date | freshness_status | rows_scored | signal_count | max_score_ticker | max_score | 扱い |
|---|---|---|---|---|---|---:|---:|---|---:|---|
| 2026-07-07 | tgs-stable-cloud-score-check-20260707T215020 | 2026-07-07 21:50:20 | 2026-07-07 | 2026-07-07 | current | 15 | 0 | 6273.T | 50 | 移行前確認 |
| 2026-07-08 | tgs-stable-cloud-score-check-20260708T211634 | 2026-07-08 21:16:34 | 2026-07-08 | 2026-07-08 | current | 15 | 0 | 6367.T | 70 | 移行前確認 |
| 2026-07-09 | tgs-stable-cloud-score-check-20260709T222751 | 2026-07-09 22:27:51 | 2026-07-09 | 2026-07-09 | current | 15 | 0 | 6367.T | 70 | 移行前確認 |

## freshness guard 証跡

stale runは削除せず、freshness guardが機能した証跡として保持する。

| Date | run_id | timestamp | requested_as_of | data_date | freshness_status | rows_scored | signal_count | max_score_ticker | max_score | 扱い |
|---|---|---|---|---|---|---:|---:|---|---:|---|
| 2026-07-07 | tgs-stable-cloud-score-check-20260707T032434 | 2026-07-07 03:24:34 | 2026-07-07 | 2026-07-03 | stale | 15 | 0 | 6273.T | 50 | HOLD / 非カウント |
| 2026-07-08 | tgs-stable-cloud-score-check-20260708T033146 | 2026-07-08 03:31:46 | 2026-07-08 | 2026-07-06 | stale | 15 | 0 | 7011.T | 70 | HOLD / 非カウント |
| 2026-07-09 | tgs-stable-cloud-score-check-20260709T015147 | 2026-07-09 01:51:47 | 2026-07-09 | 2026-07-07 | stale | 15 | 0 | 6273.T | 50 | HOLD / 非カウント |
| 2026-07-20 | tgs-stable-cloud-score-check-20260720T163821 | 2026-07-20 16:38:21 | 2026-07-20 | 2026-07-17 | stale | 15 | 0 | 6367.T | 70 | 市場休業日 / HOLD / 非カウント |

## 次段階

少額手動カナリア運用は、[TGS_STABLE_CLOUD_PHASE1_MANUAL_CANARY_CHECKLIST.md](TGS_STABLE_CLOUD_PHASE1_MANUAL_CANARY_CHECKLIST.md)に従う。
