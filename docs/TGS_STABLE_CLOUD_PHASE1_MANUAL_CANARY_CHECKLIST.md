# TGS Stable Cloud Phase1 少額手動カナリア運用チェックリスト

## 目的

Cloudflare版TGS Stable Phase1の5営業日安定確認完了後、最初の正式シグナルを少額・手動で確認する。

このチェックリストは人間による判断と手動操作のための運用手順であり、Cloud Phase1へ自動売買機能を追加するものではない。

## 対象範囲

- 開始基準日: 2026-07-27
- 対象: 開始基準日以降に新規発生する最初の正式シグナル
- 過去シグナル: 対象外
- 取引方法: 人間が内容を確認したうえで手動操作
- 自動pending登録: 使用しない
- Cloud LINE通知: 使用しない
- 証券API・自動注文・自動約定処理: 使用しない

開始基準日当日に正式シグナルがなければ、売買せず監視を継続する。

## 正式シグナル条件

次の3条件をすべて満たすこと。

- [ ] `freshness_status = current`
- [ ] `stable_score >= 90`
- [ ] `signal_expected = true`

1つでも満たさない場合はカナリア対象外とする。`signal_count=0`、staleまたはno_dataの日に取引しない。

## 1. Cloud run確認

- [ ] GitHub Actionsの対象runが`success`
- [ ] eventが`workflow_dispatch`
- [ ] branchが`main`
- [ ] trigger_originが`cloudflare_cron`
- [ ] modeが`execute`
- [ ] dispatch_keyが対象日の07:37 UTC
- [ ] requested_as_of_sourceが`external_scheduler`
- [ ] requested_as_ofが確認対象日
- [ ] data_dateがrequested_as_ofと一致
- [ ] rows_scoredが15
- [ ] pending_registration_enabledが`false`
- [ ] real_trading_enabledが`false`

## 2. Google Sheets正式台帳確認

- [ ] `TGS_Run_Log`に対象run_idが1行
- [ ] `TGS_Daily_Score_Check`に対象日15行
- [ ] 正式シグナル対象行のticker、stable_score、signal_expectedを確認
- [ ] `TGS_Pending`がヘッダーのみ
- [ ] `TGS_Positions`がヘッダーのみ
- [ ] `TGS_Trade_History`がヘッダーのみ
- [ ] `TGS_Account`がヘッダーのみ
- [ ] `TGS_Daily_Log`がヘッダーのみ
- [ ] Cloud LINE通知処理が実行されていない

## 3. 新規シグナル確認

- [ ] signal dateが2026-07-27以降
- [ ] 過去runのシグナルを再利用していない
- [ ] 同一ticker・同一signal dateのカナリアを実施済みでない
- [ ] 同日中に複数runがある場合、最新timestamp / run_idのsuccess runを使用
- [ ] stale / no_data runを正式シグナルとして扱っていない
- [ ] TradingViewまたはLINEだけを根拠にしていない

## 4. 人間による事前承認

次の項目を記入し、発注前に承認する。

| 項目 | 記録 |
|---|---|
| 確認日 |  |
| GitHub run ID |  |
| Cloud Python run_id |  |
| signal date |  |
| ticker |  |
| stable_score |  |
| signal_expected |  |
| 確認時価格 |  |
| 手動発注数量 |  |
| 想定投入額 |  |
| 許容損失額 |  |
| 承認者 |  |
| 承認時刻 |  |

- [ ] 投入額と数量が少額カナリアの範囲内
- [ ] 許容損失額を事前に決定
- [ ] 対象銘柄、数量、売買区分を再確認
- [ ] 自動処理ではなく手動操作であることを確認

## 5. 手動操作

- [ ] 証券会社の通常画面を人間が操作
- [ ] 証券APIを使用しない
- [ ] 自動注文スクリプトを使用しない
- [ ] Cloud Phase1から注文を生成しない
- [ ] 注文確定前に銘柄、数量、価格条件を再確認
- [ ] 注文結果を人間が確認

この文書は特定の注文方式、価格または数量を自動決定しない。

## 6. 実施後確認

- [ ] 実施したGitHub run IDとCloud Python run_idを記録
- [ ] 手動操作日時を記録
- [ ] 注文結果または見送り理由を記録
- [ ] Cloud Phase1の禁止5タブに新規行がない
- [ ] pending_registration_enabledが`false`のまま
- [ ] real_trading_enabledが`false`のまま
- [ ] Cloud LINE通知が無効のまま
- [ ] 証券API・自動注文・自動約定処理が無効のまま

## HOLD / 中止条件

次のいずれかに該当した場合は発注せずHOLDとする。

- GitHub Actionsがsuccess以外
- requested_as_ofとdata_dateが不一致
- freshness_statusがcurrent以外
- rows_scoredが15以外
- stable_scoreが90未満
- signal_expectedがfalse
- ArtifactとGoogle Sheets正式台帳が不一致
- 対象が2026-07-27より前のシグナル
- 同一シグナルを実施済み
- 禁止5タブに想定外の行がある
- pending、Cloud LINE、自動売買、証券APIまたは注文処理が有効
- 投入額、数量または許容損失額の人間による承認がない

## ロールバック

問題が見つかった場合:

1. 少額手動カナリアを中止する。
2. Cloud Phase1のスコア確認は継続し、正式シグナルを売買へ接続しない。
3. pending、Cloud LINE、売買、証券API、注文処理を無効のまま維持する。
4. ArtifactとGoogle Sheets正式台帳の不一致を調査する。
5. 再開は別途、人間の承認を受ける。

## 完了判定

少額手動カナリアは、正式シグナルの確認、事前承認、手動操作、実施後確認がすべて完了した場合のみ完了とする。

5営業日安定確認の完了だけを理由に、過去シグナルを遡って売買しない。
