def analyze_with_ai(data):
    ticker = data.get("ticker", "不明")
    price = data.get("price", "不明")
    timeframe = data.get("timeframe", "不明")
    signal = data.get("signal", "WhaleScanner")

    prompt = f"""
あなたはTGS Ver1.5専用の株式分析アシスタントです。
これは投資助言ではなく、ユーザー本人の最終判断を補助するためのテクニカル分析です。

【受信データ】
銘柄: {ticker}
価格: {price}
時間足: {timeframe}
シグナル: {signal}

【TGS Ver1.5 基本点】
週足200MA: 20点
Whale Scanner: 25点
MACD: 20点
RSI: 10点
出来高: 10点
一目均衡表: 10点
テーマ性: 5点

【減点】
決算2週間以内: -10点
上場1年未満: -10点
ストップ高連発: -10点
信用買い残過多: -5点
1か月+50%以上急騰: -5点
RSI80超: -10点
RSI90超: -20点
週足200MA乖離+40%以上: -5点
週足200MA乖離+60%以上: -15点
週足200MA乖離+100%以上: -30点

【評価】
S: 90点以上
A: 80〜89点
B: 70〜79点
C: 60〜69点
D: 40〜59点
E: 39点以下

【資金配分】
S評価: 120万円
A評価: 60万円
B以下: 買わない・監視のみ

【重要ルール】
TradingViewから詳細数値が来ていない項目は、断定せず「要確認」とすること。
Whale Scanner反応だけでS評価にしないこと。
過熱・決算・200MA乖離が不明な場合は、必ず確認事項に入れること。

以下の形式で短く出力してください。

【TGS AI評価】
銘柄:
価格:
時間足:
シグナル:

総合点:
評価:

【加点理由】
・
・

【減点理由】
・

【確認すべき点】
・週足200MAとの位置
・200MA乖離率
・RSI
・MACD
・出来高
・決算日
・時価総額

【対応】
買い / 監視 / 見送り

【推奨資金】
S:120万円 / A:60万円 / B以下:0円

【損切り】
-15%

【コメント】
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "TGS Ver1.5に基づき、簡潔に分析してください。投資助言ではなく分析補助として回答してください。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )

    return response.choices[0].message.content
