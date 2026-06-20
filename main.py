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
    tgs_signal = data.get("tgs_signal", "WATCH")

    prompt = f"""
あなたはTGS Ver2.0 MTF専用のテクニカル分析アシスタントです。
投資助言ではなく、ユーザー本人の最終判断を補助する分析です。

【受信データ】
銘柄: {ticker}
価格: {price}
発報時間足: {timeframe}
TGSシグナル: {tgs_signal}

RSI現在足: {data.get("rsi_now", "不明")}
RSI4時間: {data.get("rsi_4h", "不明")}
RSI日足: {data.get("rsi_d", "不明")}
RSI週足: {data.get("rsi_w", "不明")}

MACD現在足: {data.get("macd_now", "不明")}
MACD4時間: {data.get("macd_4h", "不明")}
MACD日足: {data.get("macd_d", "不明")}
MACD週足: {data.get("macd_w", "不明")}

出来高倍率: {data.get("volume_ratio", "不明")}
価格変化率: {data.get("price_change_pct", "不明")}

200MA現在足位置: {data.get("ma_now_status", "不明")}
200MA現在足乖離: {data.get("ma_now_diff", "不明")}
200MA4時間位置: {data.get("ma_4h_status", "不明")}
200MA4時間乖離: {data.get("ma_4h_diff", "不明")}
200MA日足位置: {data.get("ma_d_status", "不明")}
200MA日足乖離: {data.get("ma_d_diff", "不明")}
200MA週足位置: {data.get("ma_w_status", "不明")}
200MA週足乖離: {data.get("ma_w_diff", "不明")}

トレンド強判定: {data.get("trend_strong", "不明")}
出来高強判定: {data.get("volume_strong", "不明")}
RSI良好判定: {data.get("rsi_good", "不明")}

【TGS Ver2.0 MTF 採点ルール】
基本点100点:
・TGS BUY: +20
・4時間MACD GC: +10
・日足MACD GC: +15
・週足MACD GC: +15
・日足200MA上: +15
・週足200MA上: +15
・出来高倍率1.5倍以上: +5
・出来高倍率2.0倍以上: +10
・日足RSI40〜70: +5
・週足RSI40〜75: +5

減点:
・TGS SELL: -20
・日足RSI80超: -10
・週足RSI80超: -10
・日足200MA乖離40%以上: -5
・日足200MA乖離60%以上: -15
・日足200MA乖離100%以上: -30
・週足200MA下: -20
・日足MACD DCかつ週足MACD DC: -20

評価:
S: 90点以上
A: 80〜89点
B: 70〜79点
C: 60〜69点
D: 40〜59点
E: 39点以下

資金配分:
S: 120万円
A: 60万円
B以下: 0円、監視のみ

以下の形式で短く出力してください。

【TGS MTF評価】
銘柄:
価格:
発報時間足:
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
                "content": "TGS Ver2.0 MTFに基づき、簡潔に採点してください。数値がある場合は必ず点数化してください。"
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
            "message": "TGS MTF AI analysis sent"
        }

    except Exception as e:
        error_message = f"""TGS MTF AI分析エラー

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
