import os
import hmac
import hashlib
import base64
import time

import requests
from flask import Flask, request, abort


app = Flask(__name__)


# ==========================================
# LINE設定
# ==========================================

CHANNEL_SECRET = os.environ.get("CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN")

LINE_API = "https://api.line.me/v2/bot"


# ==========================================
# Discord設定
# ==========================================

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")


# ==========================================
# 荒らし検知設定
# ==========================================

SPAM_TIME_WINDOW = 10
SPAM_COUNT_LIMIT = 5
WARNING_COOLDOWN = 60


# ==========================================
# ユーザーごとの送信履歴
# ==========================================

user_messages = {}

last_warning_time = {}


# ==========================================
# グループごとの最後の荒らし
# ==========================================

last_spam_user = {}

# ユーザーID → 名前
user_names = {}


# ==========================================
# LINE署名確認
# ==========================================

def verify_signature(body, signature):

    if not signature:
        return False

    if not CHANNEL_SECRET:
        return False

    hash_value = hmac.new(
        CHANNEL_SECRET.encode("utf-8"),
        body,
        hashlib.sha256
    ).digest()

    expected_signature = base64.b64encode(
        hash_value
    ).decode("utf-8")

    return hmac.compare_digest(
        expected_signature,
        signature
    )


# ==========================================
# LINE返信
# ==========================================

def reply_message(reply_token, text):

    if not CHANNEL_ACCESS_TOKEN:
        return

    url = f"{LINE_API}/message/reply"

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

    try:

        response = requests.post(
            url,
            headers=headers,
            json=data,
            timeout=10
        )

        print(
            "LINE reply:",
            response.status_code,
            response.text
        )

    except Exception as e:

        print(
            "LINE reply error:",
            e
        )


# ==========================================
# Discord通知
# ==========================================

def send_discord_notification(
    user_name,
    user_id,
    text,
    count
):

    if not DISCORD_WEBHOOK_URL:

        print(
            "DISCORD_WEBHOOK_URL が設定されていません"
        )

        return

    discord_message = (
        "🚨 荒らし検知！\n\n"
        f"👤 名前：{user_name}\n"
        f"🆔 LINE User ID：{user_id}\n"
        f"🔢 連投回数：{count}回\n"
        f"💬 メッセージ：{text}"
    )

    data = {
        "content": discord_message
    }

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=data,
            timeout=10
        )

        print(
            "Discord:",
            response.status_code,
            response.text
        )

    except Exception as e:

        print(
            "Discord notification error:",
            e
        )


# ==========================================
# Discordにキック対象通知
# ==========================================

def send_discord_kick_notification(
    user_name,
    user_id
):

    if not DISCORD_WEBHOOK_URL:
        return

    discord_message = (
        "⚠️ 退会対象通知\n\n"
        f"👤 名前：{user_name}\n"
        f"🆔 LINE User ID：{user_id}\n\n"
        "管理者による確認・退会処理が必要です。"
    )

    data = {
        "content": discord_message
    }

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=data,
            timeout=10
        )

        print(
            "Discord kick notification:",
            response.status_code,
            response.text
        )

    except Exception as e:

        print(
            "Discord kick notification error:",
            e
        )


# ==========================================
# ユーザー名取得
# ==========================================

def get_user_name(user_id):

    if not CHANNEL_ACCESS_TOKEN:
        return "不明なユーザー"

    url = f"{LINE_API}/profile/{user_id}"

    headers = {
        "Authorization":
            f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:

            data = response.json()

            return data.get(
                "displayName",
                "不明なユーザー"
            )

    except Exception as e:

        print(
            "Profile error:",
            e
        )

    return "不明なユーザー"


# ==========================================
# 荒らし判定
# ==========================================

def check_spam(user_id):

    now = time.time()

    if user_id not in user_messages:

        user_messages[user_id] = []

    user_messages[user_id] = [
        timestamp
        for timestamp in user_messages[user_id]
        if now - timestamp <= SPAM_TIME_WINDOW
    ]

    user_messages[user_id].append(now)

    count = len(
        user_messages[user_id]
    )

    if count >= SPAM_COUNT_LIMIT:

        return True, count

    return False, count


# ==========================================
# LINE Webhook
# ==========================================

@app.route(
    "/callback",
    methods=["POST"]
)
def callback():

    body = request.get_data()

    signature = request.headers.get(
        "X-Line-Signature"
    )

    # ======================================
    # 署名チェック
    # ======================================

    if not verify_signature(
        body,
        signature
    ):

        abort(400)

    try:

        events = request.json.get(
            "events",
            []
        )

    except Exception:

        return "OK"


    # ======================================
    # イベント処理
    # ======================================

    for event in events:

        if event.get("type") != "message":
            continue

        message = event.get(
            "message",
            {}
        )

        if message.get("type") != "text":
            continue


        # ==================================
        # 情報取得
        # ==================================

        text = message.get(
            "text",
            ""
        ).strip()

        reply_token = event.get(
            "replyToken"
        )

        source = event.get(
            "source",
            {}
        )

        user_id = source.get(
            "userId"
        )

        group_id = source.get(
            "groupId"
        )

        if not user_id:
            continue


        # ==================================
        # ユーザー名取得
        # ==================================

        user_name = get_user_name(
            user_id
        )

        user_names[user_id] = user_name


        # ==================================
        # !id
        # ==================================

        if text == "!id":

            if reply_token:

                reply_message(
                    reply_token,
                    "🆔 あなたのLINE User ID\n\n"
                    f"{user_id}"
                )

            continue


        # ==================================
        # !kick
        # ==================================
        #
        # 直前に荒らし判定された人を対象
        #

        if text == "!kick":

            if not group_id:

                if reply_token:

                    reply_message(
                        reply_token,
                        "⚠️ このコマンドはグループ内で使用してください。"
                    )

                continue


            target_user_id = last_spam_user.get(
                group_id
            )

            if not target_user_id:

                if reply_token:

                    reply_message(
                        reply_token,
                        "⚠️ 退会対象の荒らしユーザーがありません。\n\n"
                        "まず荒らし検知を発生させてください。"
                    )

                continue


            target_name = user_names.get(
                target_user_id,
                "不明なユーザー"
            )


            # LINEにはIDを表示しない

            if reply_token:

                reply_message(
                    reply_token,
                    "⚠️ 退会対象ユーザー\n\n"
                    f"👤 {target_name}\n\n"
                    "管理者がLINEグループから"
                    "退会処理してください。"
                )


            # DiscordにはIDを通知

            send_discord_kick_notification(
                target_name,
                target_user_id
            )

            continue


        # ==================================
        # 荒らし判定
        # ==================================

        is_spam, count = check_spam(
            user_id
        )


        if is_spam:

            # グループ内の最後の荒らしを記録

            if group_id:

                last_spam_user[group_id] = user_id


            now = time.time()

            last_time = last_warning_time.get(
                user_id,
                0
            )


            # ==================================
            # 警告クールダウン
            # ==================================

            if now - last_time >= WARNING_COOLDOWN:

                last_warning_time[user_id] = now


                # ==================================
                # LINE通知
                # ==================================

                line_message = (
                    "🚨 荒らし検知！\n\n"
                    f"👤 {user_name}\n\n"
                    "⚠️ 短時間に大量のメッセージを"
                    "送信しています。\n"
                    "管理者は必要に応じて"
                    "退会処理してください。\n\n"
                    "退会対象を確認する場合は\n"
                    "!kick\n"
                    "と入力してください。"
                )


                if reply_token:

                    reply_message(
                        reply_token,
                        line_message
                    )


                # ==================================
                # Discord通知
                # ==================================

                send_discord_notification(
                    user_name,
                    user_id,
                    text,
                    count
                )


    return "OK"


# ==========================================
# ヘルスチェック
# ==========================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return "LINE Protection Bot is running!"


# ==========================================
# Render用起動
# ==========================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            8080
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
