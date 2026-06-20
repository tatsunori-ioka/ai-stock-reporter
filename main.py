from flask import Flask, request
import requests
import os
from openai import OpenAI

app = Flask(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@app.route("/")
def home():
    return "AI Stock Reporter Running"


def send_line(message):
    line_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

    headers = {
        "Authorization": f"Bearer {line_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }

    response = requests.post(
        "https://api.line.me/v2/bot/message/broadcast",
        headers=headers,
        json=payload,
        timeout=20
    )

    print("LINE status:", response.status_code)
    print("LINE response:", response.text)


def analyze_with_ai(data):
    ticker = data.get("ticker", "不明")
    price = data.get("price", "不明")
    timeframe = data.get("timeframe", "不明")

    tgs_signal = data.get("tgs_signal", "NONE")
    rsi = data.get("rsi", "不明")
    macd_status = data.get("macd_status", "不明")
    volume_ratio = data.get("volume_ratio", "不明")
    price_change_pct = data.get("price_change_pct", "不明")
    ma200_status = data.get("ma200_status", "不明")
    ma200_diff = data.get("ma200_diff", "不明")

    prompt = f"""
あなたはTGS Ver2.0専用のテクニカル分析アシスタントです。
投資助言ではなく、ユーザー本人の最終判断を補助する分析です。

【受信データ】
銘柄: {ticker}
価格: {price}
時間足: {timeframe}
TGSシグナル: {tgs_signal}
RSI: {rsi}
MACD状態: {macd_status}
出来高倍率: {volume_ratio}
価格変化率: {price_change_pct}
200MA位置: {ma200_status}
200MA乖離率: {ma200_diff}

【採点ルール】
TGS BUY: +25
TGS SELL: 0
MACD GC: +20
MACD DC: 0
RSI 40〜60: +10
RSI 30〜40: +8
RSI 60〜70: +6
RSI 70〜80: +3
RSI 80超: -10
出来高倍率2倍以上: +10
出来高倍率1.5倍以上: +7
出来高倍率1倍以上: +5
200MA上: +20
200MA下: 0
200MA乖離5〜25%: +10
200MA乖離25〜40%: +5
200MA乖離40%以上: -5
200MA乖離60%以上: -15
200MA乖離100%以上: -30

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
        temperature=0.2,
        timeout=30
    )

    return response.choices[0].message.content


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    print("TradingView data:", data)

    try:
        ai_message = analyze_with_ai(data)
        print("AI message:", ai_message)

        send_line(ai_message)

        return {
            "status": "ok",
            "message": "TGS AI analysis sent"
        }

    except Exception as e:
        error_message = f"""TGS AI分析エラー

受信データ:
{data}

エラー:
{str(e)}
"""
        print(error_message)

        try:
            send_line(error_message)
        except Exception as line_error:
            print("LINE error:", str(line_error))

        return {
            "status": "error",
            "error": str(e)
        }, 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
