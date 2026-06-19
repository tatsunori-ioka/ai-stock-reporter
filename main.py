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
        json=payload
    )

    print("LINE status:", response.status_code)
    print("LINE response:", response.text)

def analyze_with_ai(data):
    ticker = data.get("ticker", "不明")
    price = data.get("price", "不明")
    timeframe = data.get("timeframe", "不明")
    signal = data.get("signal", "WhaleScanner")

    prompt = f"""
あなたは日本株と暗号資産のテクニカル分析アシスタントです。
ユーザーはテクニカル中心で、週足・日足・4時間足、200MA、MACD、RSI、出来高、Whale Scannerを重視します。
PER、PBR、決算短信は今回は評価対象にしません。

以下のWhale Scanner反応を、100点満点で簡易評価してください。

銘柄: {ticker}
価格: {price}
時間足: {timeframe}
シグナル: {signal}

評価ルール:
- Whale反応: 10点
- 週足判定: 25点
- 日足判定: 20点
- 4時間判定: 10点
- MACD: 15点
- RSI: 10点
- 出来高: 10点

ただし、TradingViewから詳細数値が来ていない場合は、断定せず「要確認」としてください。
最後に、以下の形式で短く出力してください。

【AI評価】
銘柄:
価格:
時間足:
総合点:
評価:
理由:
確認すべき点:
対応:
損切り目安:
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "投資助言ではなく、テクニカル確認用の分析補助として簡潔に回答してください。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )

    return response.choices[0].message.content

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    print("TradingView data:", data)

    try:
        ai_message = analyze_with_ai(data)
        send_line(ai_message)
        return {"status": "ok", "message": "AI analysis sent"}
    except Exception as e:
        error_message = f"""AI分析エラー

受信データ:
{data}

エラー:
{str(e)}
"""
        print(error_message)
        send_line(error_message)
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
