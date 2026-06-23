from flask import Flask, request, jsonify
import requests
import os

from stable_webhook_core import process_stable_webhook
from stable_paper_daily import parse_date, run_daily


app = Flask(__name__)


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

    if not line_token:
        print("LINE token is missing")
        return

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


def calculate_score(data):
    score = 0
    plus = []
    minus = []

    macd_4h = data.get("macd_4h", "")
    macd_d = data.get("macd_d", "")
    macd_w = data.get("macd_w", "")

    ma_d_status = data.get("ma_d_status", "")
    ma_w_status = data.get("ma_w_status", "")

    rsi_d_available = str(data.get("rsi_d_available", "true")).lower() == "true"
    rsi_w_available = str(data.get("rsi_w_available", "true")).lower() == "true"

    rsi_d = to_float(data.get("rsi_d"))
    rsi_w = to_float(data.get("rsi_w"))
    volume_ratio = to_float(data.get("volume_ratio"))
    ma_d_diff = to_float(data.get("ma_d_diff"))

    if macd_4h == "GC":
        score += 10
        plus.append("4H MACD GC +10")

    if macd_d == "GC":
        score += 15
        plus.append("日足MACD GC +15")

    if macd_w == "GC":
        score += 15
        plus.append("週足MACD GC +15")

    if ma_d_status == "above":
        score += 15
        plus.append("日足200MA上 +15")

    if ma_w_status == "above":
        score += 15
        plus.append("週足200MA上 +15")

    if rsi_d_available and 40 <= rsi_d <= 70:
        score += 5
        plus.append("日足RSI良好 +5")

    if rsi_w_available and 40 <= rsi_w <= 75:
        score += 5
        plus.append("週足RSI良好 +5")

    if volume_ratio >= 2.0:
        score += 10
        plus.append("出来高2倍以上 +10")
    elif volume_ratio >= 1.5:
        score += 5
        plus.append("出来高1.5倍以上 +5")

    if ma_d_status == "below":
        score -= 25
        minus.append("日足200MA下 -25")

    if ma_w_status == "below":
        score -= 30
        minus.append("週足200MA下 -30")

    if volume_ratio == 0:
        score -= 10
        minus.append("出来高取得なし/0 -10")

    if rsi_d_available and rsi_d >= 80:
        score -= 10
        minus.append("日足RSI80超 -10")

    if rsi_w_available and rsi_w >= 80:
        score -= 10
        minus.append("週足RSI80超 -10")

    if rsi_d_available and rsi_d <= 30:
        score -= 10
        minus.append("日足RSI30以下 -10")

    if rsi_w_available and rsi_w <= 30:
        score -= 10
        minus.append("週足RSI30以下 -10")

    if ma_d_diff >= 100:
        score -= 30
        minus.append("日足200MA乖離100%以上 -30")
    elif ma_d_diff >= 60:
        score -= 15
        minus.append("日足200MA乖離60%以上 -15")
    elif ma_d_diff >= 40:
        score -= 5
        minus.append("日足200MA乖離40%以上 -5")

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

    return score, grade, action, capital, plus, minus


def make_comment(grade, data):
    ma_d_status = data.get("ma_d_status", "")
    volume_ratio = to_float(data.get("volume_ratio"))

    if grade in ["S", "A"]:
        return "TGS条件を満たす買い候補です。損切り-15%前提で検討。"

    if grade in ["B", "C"]:
        return "条件は悪くありませんが、A評価未満のため監視です。"

    if ma_d_status == "below" and volume_ratio == 0:
        return "MACDは良好でも、日足200MA下・出来高不足のため見送りです。"

    return "弱い条件が多いため、現時点では見送りです。"


def make_message(data):
    score, grade, action, capital, plus, minus = calculate_score(data)

    ticker = data.get("ticker", "不明")
    price = data.get("price", "不明")
    timeframe = data.get("timeframe", "不明")

    plus_text = "\n".join([f"・{p}" for p in plus]) if plus else "・なし"
    minus_text = "\n".join([f"・{m}" for m in minus]) if minus else "・なし"
    comment = make_comment(grade, data)

    return f"""【TGS Ver3.1】

銘柄: {ticker}
価格: {price}
時間足: {timeframe}

総合点: {score}
評価: {grade}
対応: {action}
推奨資金: {capital}

【加点】
{plus_text}

【減点】
{minus_text}

損切り目安: -15%

コメント:
{comment}
"""


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print("TradingView data:", data)

    try:
        score, grade, action, capital, plus, minus = calculate_score(data)

        if score < 60:
            print(f"Skip LINE: score {score} < 60")
            return {
                "status": "skipped",
                "reason": "score below 60",
                "score": score,
                "ticker": data.get("ticker", "不明")
            }

        message = make_message(data)
        print("TGS message:", message)
        send_line(message)

        return {
            "status": "ok",
            "message": "TGS Ver3.1 sent",
            "score": score,
            "ticker": data.get("ticker", "不明")
        }

    except Exception as e:
        error_message = f"""TGS Ver3.1 エラー

受信データ:
{data}

エラー:
{str(e)}
"""
        print(error_message)
        send_line(error_message)
        return {"status": "error", "error": str(e)}, 500


@app.route("/webhook/tradingview/stable-v1", methods=["POST"])
def tradingview_stable_v1():
    payload = request.get_json(force=True)
    result = process_stable_webhook(payload, send_line_enabled=True)
    print("Stable payload:", payload)
    print("Stable result:", result)
    status = 200 if result["accepted"] else 202
    return jsonify({"ok": result["accepted"], **result}), status


@app.route("/tasks/stable-paper-daily", methods=["POST"])
def stable_paper_daily_task():
    expected_token = os.getenv("STABLE_TASK_TOKEN")
    provided_token = request.headers.get("X-Stable-Task-Token", "")
    if not expected_token:
        return jsonify({"ok": False, "reason": "STABLE_TASK_TOKEN_not_set"}), 500
    if provided_token != expected_token:
        return jsonify({"ok": False, "reason": "unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    as_of = parse_date(str(payload.get("as_of", ""))) if payload.get("as_of") else None
    result = run_daily(as_of)
    print("Stable paper daily result:", result)
    return jsonify(result), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
