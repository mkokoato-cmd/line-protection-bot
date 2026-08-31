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
    if not CHANNEL_SECRET:
        return False

    hash_value = hmac.new(
        CHANNEL_SECRET.encode("utf-8"),
        body,
        hashlib.sha256
    ).digest()

    expected_signature = base64.b64encode(hash_value).decode("utf-8")

    return hmac.compare_digest(
        expected_signature,
        signature or ""
    )


def is_spam(user_id):
    now = time.time()

    if user_id not in user_messages:
        user_messages[user_id] = []

    user_messages[user_id] = [
        t for t in user_messages[user_id]
        if now - t < SPAM_WINDOW
    ]

    user_messages[user_id].append(now)

    return len(user_messages[user_id]) > SPAM_LIMIT


def reply_message(reply_token, message):
    if not CHANNEL_ACCESS_TOKEN:
        return

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
                "text": message
            }
        ]
    }

    requests.post(
        url,
        headers=headers,
        json=data,
        timeout=10
    )


@app.route("/callback", methods=["POST"])
def callback():

    body = request.get_data()

    signature = request.headers.get(
        "X-Line-Signature",
        ""
    )

    if not verify_signature(body, signature):
        abort(400)

    data = request.get_json(silent=True) or {}

    events = data.get("events", [])

    for event in events:

        event_type = event.get("type")

        # =====================================
        # グループメンバー退出検知
        # =====================================

        if event_type == "memberLeft":

            reply_token = event.get("replyToken")

            if reply_token:
                reply_message(
                    reply_token,
                    "🚨 メンバー退出を検知しました。\n"
                    "グループからメンバーが退出しました。"
                )

            continue

        # =====================================
        # メッセージ以外は無視
        # =====================================

        if event_type != "message":
            continue

        message = event.get("message", {})

        if message.get("type") != "text":
            continue

        reply_token = event.get("replyToken")

        source = event.get("source", {})

        user_id = source.get(
            "userId",
            "unknown"
        )

        text = message.get("text", "")

        # =====================================
        # スパム検知
        # =====================================

        if is_spam(user_id):

            if reply_token:
                reply_message(
                    reply_token,
                    "⚠️ 短時間にたくさんのメッセージが送られています。"
                    " 少し時間をおいてください。"
                )

            continue

        # =====================================
        # 不適切な言葉の検知
        # =====================================

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

            continue

    return "OK"


if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 8080)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
