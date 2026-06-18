from flask import Flask, request
import requests
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "AI Stock Reporter Running"

@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.json

    message = f"""
Whale Scanner反応

銘柄:
{data}

確認してください。
"""

    line_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

    headers = {
        "Authorization": f"Bearer {line_token}"
    }

    payload = {
        "message": message
    }

    requests.post(
        "https://api.line.me/v2/bot/message/broadcast",
        headers=headers,
        json=payload
    )

    return {"status": "ok"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
