# TGS Stable Ver1.0 Cloud Phase1 5営業日安定確認

## 正式判定方針

Cloud Phase1の正式判定は Cloud Python正本 + Google Sheets正式台帳で行う。

正式シグナル条件:
- freshness_status = current
- stable_score >= 90
- signal_expected = true

TradingView / LINE通知は参考通知扱い。
Cloud Phase1では pending登録、LINE通知、売買処理、証券API、注文処理は有効化しない。

## 進捗

| Day | Date | 判定 | run_id | timestamp | as_of | data_date | freshness_status | rows_scored | signal_count | max_score_ticker | max_score | 正式シグナル | 備考 |
|---:|---|---|---|---|---|---|---|---:|---:|---|---:|---|---|
| Day 1 | 2026-07-07 | OK | tgs-stable-cloud-score-check-20260707T215020 | 2026-07-07 21:50:20 | 2026-07-07 | 2026-07-07 | current | 15 | 0 | 6273.T | 50 | なし | 再実行分でcurrent確認 |
| Day 2 | 2026-07-08 | OK | tgs-stable-cloud-score-check-20260708T211634 | 2026-07-08 21:16:34 | 2026-07-08 | 2026-07-08 | current | 15 | 0 | 6367.T | 70 | なし | 再実行分でcurrent確認 |
| Day 3 | 2026-07-09 | 未確認 |  |  |  |  |  |  |  |  |  |  |  |
| Day 4 | 2026-07-10 | 未確認 |  |  |  |  |  |  |  |  |  |  |  |
| Day 5 | 2026-07-13 | 未確認 |  |  |  |  |  |  |  |  |  |  |  |

## stale guard 確認ログ

| Date | run_id | timestamp | as_of | data_date | freshness_status | rows_scored | signal_count | max_score_ticker | max_score | 扱い |
|---|---|---|---|---|---|---:|---:|---|---:|---|
| 2026-07-07 | tgs-stable-cloud-score-check-20260707T032434 | 2026-07-07 03:24:34 | 2026-07-07 | 2026-07-03 | stale | 15 | 0 | 6273.T | 50 | HOLD / 非カウント |
| 2026-07-08 | tgs-stable-cloud-score-check-20260708T033146 | 2026-07-08 03:31:46 | 2026-07-08 | 2026-07-06 | stale | 15 | 0 | 7011.T | 70 | HOLD / 非カウント |

## 現在の状態

2026-07-08時点:

- Day 1: OK
- Day 2: OK
- Day 3: 未確認
- Day 4: 未確認
- Day 5: 未確認

5営業日安定確認の進捗:
2 / 5 OK

## Day 2詳細

Cloud Phase1 5営業日安定確認

Day 2: 2026-07-08
判定: OK

判定対象run_id:
tgs-stable-cloud-score-check-20260708T211634

timestamp:
2026-07-08 21:16:34

status:
success

as_of:
2026-07-08

data_date:
2026-07-08

freshness_status:
current

rows_scored:
15

signal_count:
0

max_score_ticker:
6367.T

max_score:
70

不要タブ書き込み:
なし

Cloud発LINE通知:
なし

正式シグナル:
なし

理由:
Cloud正本で data_date と as_of が一致し、freshness_status=current、15銘柄スコア確認済み。max_score=70でScore90未満のため正式シグナルなし。

## 次回確認

Day 3:
2026-07-09

確認条件:
- GitHub Actions success
- TGS_Run_Log に対象runあり
- as_of = 2026-07-09
- data_date = 2026-07-09
- freshness_status = current
- rows_scored = 15
- TGS_Daily_Score_Check に15銘柄分あり
- TGS_Pending / TGS_Positions / TGS_Trade_History / TGS_Account / TGS_Daily_Log に不要書き込みなし
- Cloud発LINE通知なし
