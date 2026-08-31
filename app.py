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

SPAM_LIMIT = 5
SPAM_WINDOW = 10

user_messages = {}


def verify_signature(body, signature):
    if not CHANNEL_SECRET or not signature:
        return False

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
        "Authorization": "Bearer " + CHANNEL_ACCESS_TOKEN
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

    response.raise_for_status()


def is_spam(user_id):
    now = time.time()

    messages = user_messages.get(user_id, [])

    messages = [
        timestamp
        for timestamp in messages
        if now - timestamp < SPAM_WINDOW
    ]

    messages.append(now)
    user_messages[user_id] = messages

    return len(messages) > SPAM_LIMIT


@app.route("/", methods=["GET"])
def index():
    return "LINE Protection Bot is running."


@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")

    if not verify_signature(body, signature):
        abort(400)

    events = request.get_json().get("events", [])

    for event in events:
        if event.get("type") != "message":
            continue

        if event.get("message", {}).get("type") != "text":
            continue

        reply_token = event.get("replyToken")

        source = event.get("source", {})
        user_id = source.get("userId", "unknown")

        text = event["message"]["text"]

        if is_spam(user_id):
            if reply_token:
                reply_message(
                    reply_token,
                    "⚠️ 短時間にたくさんのメッセージが送られています。"
                )
            continue

        ng_words = [
            "死ね",
            "消えろ",
            "殺す"
        ]

        if any(word in text for word in ng_words):
            if reply_token:
                reply_message(
                    reply_token,
                    "⚠️ 不適切な言葉が検出されました。"
                )

    return "OK"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
