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

# 何秒以内の連投を調べるか
SPAM_TIME_WINDOW = 10

# 何回以上送ったら荒らしと判定するか
SPAM_COUNT_LIMIT = 5

# 同じ荒らしについて何秒ごとに警告するか
WARNING_COOLDOWN = 60


# ==========================================
# ユーザーごとの送信履歴
# ==========================================

user_messages = {}

# 最後に警告した時間
last_warning_time = {}


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

    # ======================================
    # DiscordだけにUser IDを表示
    # ======================================

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

    # 古い履歴を削除
    user_messages[user_id] = [
        timestamp
        for timestamp in user_messages[user_id]
        if now - timestamp <= SPAM_TIME_WINDOW
    ]

    # 今回のメッセージを追加
    user_messages[user_id].append(now)

    count = len(
        user_messages[user_id]
    )

    # 連投回数が基準以上なら荒らし
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

        # メッセージイベント以外は無視
        if event.get("type") != "message":

            continue

        message = event.get(
            "message",
            {}
        )

        # テキスト以外は無視
        if message.get("type") != "text":

            continue

        # ==================================
        # 必要情報取得
        # ==================================

        text = message.get(
            "text",
            ""
        )

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

        # User IDが取れなければ処理しない
        if not user_id:

            continue


        # ==================================
        # ユーザー名取得
        # ==================================

        user_name = get_user_name(
            user_id
        )


        # ==================================
        # LINE User ID表示コマンド
        # ==================================

        if text.strip() == "!id":

            if reply_token:

                reply_message(
                    reply_token,
                    "🆔 あなたのLINE User ID\n\n"
                    f"{user_id}"
                )

            # !id は荒らしカウントしない
            continue


        # ==================================
        # 荒らし判定
        # ==================================

        is_spam, count = check_spam(
            user_id
        )

        if is_spam:

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
                #
                # ★LINEにはUser IDを表示しない
                # ==================================

                line_message = (
                    "🚨 荒らし検知！\n\n"
                    f"👤 {user_name}\n\n"
                    "⚠️ 短時間に大量のメッセージを"
                    "送信しています。\n"
                    "管理者は必要に応じて退会処理"
                    "してください。"
                )

                if reply_token:

                    reply_message(
                        reply_token,
                        line_message
                    )


                # ==================================
                # Discord通知
                #
                # ★User IDはDiscordだけ
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
