from flask import Flask, request
import requests
import os
from openai import OpenAI

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@app.route("/")
def home():
    return "AI Stock Reporter Running"


def to_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def send_line(message):
    line_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

    headers = {
        "Authorization": f"Bearer {line_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "messages": [{"type": "text", "text": message}]
    }

    response = requests.post(
        "https://api.line.me/v2/bot/message/broadcast",
        headers=headers,
        json=payload,
        timeout=20
    )

    print("LINE status:", response.status_code)
    print("LINE response:", response.text)


def calculate_tgs_score(data):
    score = 0
    reasons = []
    penalties = []

    tgs_signal = data.get("tgs_signal", "WATCH")

    macd_4h = data.get("macd_4h", "")
    macd_d = data.get("macd_d", "")
    macd_w = data.get("macd_w", "")

    ma_d_status = data.get("ma_d_status", "")
    ma_w_status = data.get("ma_w_status", "")

    rsi_d = to_float(data.get("rsi_d"))
    rsi_w = to_float(data.get("rsi_w"))
    volume_ratio = to_float(data.get("volume_ratio"))
    ma_d_diff = to_float(data.get("ma_d_diff"))

    if tgs_signal == "BUY":
        score += 20
        reasons.append("TGS BUY +20")
    elif tgs_signal == "SELL":
        score -= 20
        penalties.append("TGS SELL -20")

    if macd_4h == "GC":
        score += 10
        reasons.append("4時間MACD GC +10")

    if macd_d == "GC":
        score += 15
        reasons.append("日足MACD GC +15")

    if macd_w == "GC":
        score += 15
        reasons.append("週足MACD GC +15")

    if ma_d_status == "above":
        score += 15
        reasons.append("日足200MA上 +15")

    if ma_w_status == "above":
        score += 15
        reasons.append("週足200MA上 +15")
    else:
        score -= 20
        penalties.append("週足200MA下 -20")

    if volume_ratio >= 2.0:
        score += 10
        reasons.append("出来高倍率2.0倍以上 +10")
    elif volume_ratio >= 1.5:
        score += 5
        reasons.append("出来高倍率1.5倍以上 +5")

    if 40 <= rsi_d <= 70:
        score += 5
        reasons.append("日足RSI40〜70 +5")

    if 40 <= rsi_w <= 75:
        score += 5
        reasons.append("週足RSI40〜75 +5")

    if rsi_d >= 80:
        score -= 10
        penalties.append("日足RSI80超 -10")

    if rsi_w >= 80:
        score -= 10
        penalties.append("週足RSI80超 -10")

    if ma_d_diff >= 100:
        score -= 30
        penalties.append("日足200MA乖離100%以上 -30")
    elif ma_d_diff >= 60:
        score -= 15
        penalties.append("日足200MA乖離60%以上 -15")
    elif ma_d_diff >= 40:
        score -= 5
        penalties.append("日足200MA乖離40%以上 -5")

    if macd_d == "DC" and macd_w == "DC":
        score -= 20
        penalties.append("日足MACD DCかつ週足MACD DC -20")

    score = max(0, min(100, score))

    if score >= 90:
        grade = "S"
        action = "買い候補"
        capital = "120万円"
    elif score >= 80:
        grade = "A"
        action = "買い候補"
        capital = "60万円"
    elif score >= 70:
        grade = "B"
        action = "監視"
        capital = "0円"
    elif score >= 60:
        grade = "C"
        action = "監視"
        capital = "0円"
    elif score >= 40:
        grade = "D"
        action = "見送り"
        capital = "0円"
    else:
        grade = "E"
        action = "見送り"
        capital = "0円"

    return score, grade, action, capital, reasons, penalties


def make_ai_comment(data, score, grade, action):
    prompt = f"""
以下のTGS固定採点結果に対して、短くコメントしてください。
投資助言ではなく、テクニカル確認用の補助コメントです。

銘柄: {data.get("ticker")}
価格: {data.get("price")}
時間足: {data.get("timeframe")}
点数: {score}
評価: {grade}
対応: {action}

RSI日足: {data.get("rsi_d")}
RSI週足: {data.get("rsi_w")}
MACD4時間: {data.get("macd_4h")}
MACD日足: {data.get("macd_d")}
MACD週足: {data.get("macd_w")}
出来高倍率: {data.get("volume_ratio")}
日足200MA位置: {data.get("ma_d_status")}
週足200MA位置: {data.get("ma_w_status")}
日足200MA乖離: {data.get("ma_d_diff")}

50文字〜100文字程度で、なぜ買い/監視/見送りなのか説明してください。
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "簡潔なテクニカルコメントだけを返してください。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        timeout=20
    )

    return response.choices[0].message.content


def analyze_with_ai(data):
    score, grade, action, capital, reasons, penalties = calculate_tgs_score(data)

    ticker = data.get("ticker", "不明")
    price = data.get("price", "不明")
    timeframe = data.get("timeframe", "不明")

    try:
        comment = make_ai_comment(data, score, grade, action)
    except Exception as e:
        comment = f"AIコメント生成エラー: {str(e)}"

    reasons_text = "\n".join([f"・{r}" for r in reasons]) if reasons else "・なし"
    penalties_text = "\n".join([f"・{p}" for p in penalties]) if penalties else "・なし"

    message = f"""【TGS Ver2.1 固定採点】

銘柄: {ticker}
価格: {price}
時間足: {timeframe}

総合点: {score}
評価: {grade}
対応: {action}

【加点理由】
{reasons_text}

【減点理由】
{penalties_text}

【推奨資金】
{capital}

【損切り目安】
価格の-15%

【AIコメント】
{comment}
"""

    return message


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    print("TradingView data:", data)

    try:
        message = analyze_with_ai(data)
        print("TGS message:", message)

        send_line(message)

        return {"status": "ok", "message": "TGS Ver2.1 sent"}

    except Exception as e:
        error_message = f"""TGS Ver2.1 エラー

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

        return {"status": "error", "error": str(e)}, 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
