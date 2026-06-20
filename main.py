from flask import Flask, request
import requests
import os

app = Flask(__name__)


@app.route("/")
def home():
    return "AI Stock Reporter Running - TGS Lite"


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


def make_action(score):
    if score >= 90:
        return "S", "買い候補", "120万円"
    elif score >= 80:
        return "A", "買い候補", "60万円"
    elif score >= 70:
        return "B", "監視", "0円"
    elif score >= 60:
        return "C", "監視", "0円"
    elif score >= 40:
        return "D", "見送り", "0円"
    else:
        return "E", "見送り", "0円"


def make_comment(score, grade, data):
    macd_d = data.get("macd_d", "")
    macd_w = data.get("macd_w", "")
    ma_d_status = data.get("ma_d_status", "")
    ma_w_status = data.get("ma_w_status", "")

    rsi_d = to_float(data.get("rsi_d"))
    rsi_w = to_float(data.get("rsi_w"))

    if grade in ["S", "A"]:
        return "日足・週足の条件が強く、TGS上は買い候補です。損切り-15%前提で確認。"

    if grade in ["B", "C"]:
        return "一部条件は良いですが、A評価未満のため監視です。追加確認が必要です。"

    if ma_d_status == "below":
        return "日足200MA下のため弱い判定です。新規買いは見送り優先です。"

    if macd_d == "DC" and macd_w == "DC":
        return "日足・週足MACDが弱く、トレンド不足です。"

    if rsi_d >= 80 or rsi_w >= 80:
        return "RSI過熱のため、高値掴みに注意です。"

    return "TGS条件が不足しているため、現時点では見送りです。"


def make_message(data):
    ticker = data.get("ticker", "不明")
    price = data.get("price", "不明")
    timeframe = data.get("timeframe", "不明")

    score = int(to_float(data.get("score")))
    grade_from_tv = data.get("grade", "")

    grade, action, capital = make_action(score)

    # TradingView側のgradeがあれば参考表示
    if grade_from_tv and grade_from_tv != grade:
        grade_note = f"TV評価:{grade_from_tv} / Python評価:{grade}"
    else:
        grade_note = grade

    rsi_d = data.get("rsi_d", "不明")
    rsi_w = data.get("rsi_w", "不明")
    macd_d = data.get("macd_d", "不明")
    macd_w = data.get("macd_w", "不明")
    ma_d_status = data.get("ma_d_status", "不明")
    ma_d_diff = data.get("ma_d_diff", "不明")
    ma_w_status = data.get("ma_w_status", "不明")
    ma_w_diff = data.get("ma_w_diff", "不明")

    comment = make_comment(score, grade, data)

    return f"""【TGS Lite評価】

銘柄: {ticker}
価格: {price}
時間足: {timeframe}

総合点: {score}
評価: {grade_note}
対応: {action}
推奨資金: {capital}

【日足】
RSI: {rsi_d}
MACD: {macd_d}
200MA: {ma_d_status}
乖離率: {ma_d_diff}%

【週足】
RSI: {rsi_w}
MACD: {macd_w}
200MA: {ma_w_status}
乖離率: {ma_w_diff}%

損切り目安: -15%

コメント:
{comment}
"""


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print("TradingView data:", data)

    try:
        message = make_message(data)
        print("TGS Lite message:", message)
        send_line(message)
        return {"status": "ok", "message": "TGS Lite sent"}

    except Exception as e:
        error_message = f"""TGS Lite エラー

受信データ:
{data}

エラー:
{str(e)}
"""
        print(error_message)
        send_line(error_message)
        return {"status": "error", "error": str(e)}, 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
