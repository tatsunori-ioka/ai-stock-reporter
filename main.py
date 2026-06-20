def analyze_with_ai(data):
    ticker = data.get("ticker", "不明")
    price = data.get("price", "不明")
    timeframe = data.get("timeframe", "不明")
    signal_type = data.get("type", data.get("signal", "不明"))

    rsi = data.get("rsi", "不明")
    macd_status = data.get("macd_status", "不明")
    volume_ratio = data.get("volume_ratio", "不明")
    price_change_pct = data.get("price_change_pct", "不明")
    ma200_status = data.get("ma200_status", "不明")
    ma200_diff = data.get("ma200_diff", "不明")
    tgs_signal = data.get("tgs_signal", "NONE")

    prompt = f"""
あなたはTGS Ver2.0専用のテクニカル分析アシスタントです。
投資助言ではなく、ユーザー本人の最終判断を補助する分析です。

【受信データ】
銘柄: {ticker}
価格: {price}
時間足: {timeframe}
シグナル種別: {signal_type}
TGSシグナル: {tgs_signal}
RSI: {rsi}
MACD状態: {macd_status}
出来高倍率: {volume_ratio}
価格変化率: {price_change_pct}
200MA位置: {ma200_status}
200MA乖離率: {ma200_diff}

【TGS Ver2.0 採点ルール】
基本点:
・TGS BUY: +25点
・TGS SELL: 0点
・MACD GC: +20点
・MACD DC: 0点
・RSI 40〜60: +10点
・RSI 30〜40: +8点
・RSI 60〜70: +6点
・RSI 70〜80: +3点
・RSI 80超: -10点
・出来高倍率 2倍以上: +10点
・出来高倍率 1.5倍以上: +7点
・出来高倍率 1.0倍以上: +5点
・200MA上: +20点
・200MA下: 0点
・200MA乖離 5〜25%: +10点
・200MA乖離 25〜40%: +5点
・200MA乖離 40%以上: -5点
・200MA乖離 60%以上: -15点
・200MA乖離 100%以上: -30点

【評価】
S: 90点以上
A: 80〜89点
B: 70〜79点
C: 60〜69点
D: 40〜59点
E: 39点以下

【資金配分】
S: 120万円
A: 60万円
B以下: 0円、監視のみ

以下の形式で短く出力してください。

【TGS評価】
銘柄:
価格:
時間足:
総合点:
評価:

【加点理由】
・
・

【減点理由】
・

【対応】
買い / 監視 / 見送り

【推奨資金】
円

【損切り目安】
価格の-15%

【コメント】
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": "TGS Ver2.0に基づき、簡潔に採点してください。数値がある場合は必ず点数化してください。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.2
    )

    return response.choices[0].message.content
