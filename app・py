import os
import time
import hmac
import hashlib
import base64
import requests

from flask import Flask, request, abort

app = Flask(__name__)

CHANNEL_SECRET = os.environ.get("CHANNEL_SECRET", "")
CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN", "")

# 荒らし対策用の設定
SPAM_LIMIT = 5
SPAM_WINDOW = 10

user_messages = {}


def verify_signature(body, signature):
    hash_value = hmac.new(
        CHANNEL_SECRET.encode("utf-8"),
        body,
        hashlib.sha256
    ).digest()

    expected_signature = base64.b64encode(hash_value).decode("utf-8")

    return hmac.compare_digest(expected_signature, signature)


def reply_message(reply_token, text):
    url = "https://api.line.me/v2/bot/message/reply"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

    data = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": text
            }
        ]
    }

    response = requests.post(
        url,
        headers=headers,
        json=data,
        timeout=10
    )

    return response


@app.route("/", methods=["GET"])
def home():
    return "LINE Protection Bot is running!"


@app.route("/callback", methods=["POST"])
def callback():

    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")

    if not verify_signature(body, signature):
        abort(400)

    event_data = request.get_json()

    for event in event_data.get("events", []):

        if event.get("type") != "message":
            continue

        message = event.get("message", {})

        if message.get("type") != "text":
            continue

        user_id = event.get("source", {}).get("userId", "unknown")
        text = message.get("text", "")
        now = time.time()

        # ユーザーごとのメッセージ履歴
        if user_id not in user_messages:
            user_messages[user_id] = []

        user_messages[user_id].append(now)

        # 10秒より古い記録を削除
        user_messages[user_id] = [
            t for t in user_messages[user_id]
            if now - t <= SPAM_WINDOW
        ]

        # 短時間に大量投稿した場合
        if len(user_messages[user_id]) >= SPAM_LIMIT:

            reply_token = event.get("replyToken")

            if reply_token:
                reply_message(
                    reply_token,
                    "⚠️ 荒らし・連投を検知しました。\n短時間の連続投稿は控えてください。"
                )

            user_messages[user_id] = []

        # 通常メッセージ
        else:
            print(f"Message: {text}")

    return "OK"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
