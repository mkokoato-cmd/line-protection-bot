import os
import hmac
import hashlib
import base64
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

DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL"
)


# ==========================================
# 禁句設定
# ==========================================

FORBIDDEN_WORDS = [
    "殺す",
    "死ね",
    "死んで",
    "キモイ"
]


# ==========================================
# 荒らしユーザー保存
# ==========================================

# グループごとの最後の荒らしユーザー
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
        "Authorization": (
            f"Bearer {CHANNEL_ACCESS_TOKEN}"
        )
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
# Discord荒らし通知
# ==========================================

def send_discord_notification(
    user_name,
    user_id,
    text
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
# Discord禁句通知
# ==========================================

def send_discord_forbidden_notification(
    user_name,
    user_id,
    text,
    forbidden_word
):

    if not DISCORD_WEBHOOK_URL:

        print(
            "DISCORD_WEBHOOK_URL が設定されていません"
        )

        return

    discord_message = (
        "🚫 禁句検知！\n\n"
        f"👤 名前：{user_name}\n"
        f"🆔 LINE User ID：{user_id}\n"
        f"🚨 禁句：{forbidden_word}\n"
        f"💬 メッセージ：{text}\n\n"
        "⚠️ 荒らしとして自動登録しました。"
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
            "Discord forbidden:",
            response.status_code,
            response.text
        )

    except Exception as e:

        print(
            "Discord forbidden notification error:",
            e
        )


# ==========================================
# Discordキック対象通知
# ==========================================

def send_discord_kick_notification(
    user_name,
    user_id
):

    if not DISCORD_WEBHOOK_URL:
        return

    discord_message = (
        "⚠️ 退会対象ユーザー\n\n"
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

        # メッセージ以外は無視
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


        # User IDが取れない場合
        if not user_id:
            continue


        # ==================================
        # ユーザー名
        # ==================================

        user_name = get_user_name(
            user_id
        )

        user_names[user_id] = user_name


        # ==================================
        # 禁句検知
        # ==================================

        detected_forbidden_word = None

        for forbidden_word in FORBIDDEN_WORDS:

            if forbidden_word in text:

                detected_forbidden_word = (
                    forbidden_word
                )

                break


        # ==================================
        # 禁句が見つかった場合
        # ==================================

        if detected_forbidden_word:

            print(
                "禁句検知:",
                user_name,
                user_id,
                detected_forbidden_word,
                text
            )


            # ==================================
            # 荒らしユーザーとして登録
            # ==================================

            if group_id:

                last_spam_user[
                    group_id
                ] = user_id


            # ==================================
            # Discord禁句通知
            # ==================================

            send_discord_forbidden_notification(
                user_name,
                user_id,
                text,
                detected_forbidden_word
            )


            # ==================================
            # Discord荒らし通知
            # ==================================

            send_discord_notification(
                user_name,
                user_id,
                text
            )


            continue


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
        # !荒らし
        # ==================================

        if text == "!荒らし":

            # グループ内で使用された場合
            if group_id:

                last_spam_user[
                    group_id
                ] = user_id


            # ==================================
            # LINE通知
            # ==================================

            line_message = (
                "🚨 荒らし検知！\n\n"
                f"👤 {user_name}\n\n"
                "⚠️ 荒らしとして登録しました。\n\n"
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
                text
            )

            continue


        # ==================================
        # !kick
        # ==================================

        if text == "!kick":

            # グループ以外では使用不可
            if not group_id:

                if reply_token:

                    reply_message(
                        reply_token,
                        "⚠️ このコマンドは"
                        "グループ内で使用してください。"
                    )

                continue


            # ==================================
            # 最後の荒らしユーザー
            # ==================================

            target_user_id = last_spam_user.get(
                group_id
            )


            if not target_user_id:

                if reply_token:

                    reply_message(
                        reply_token,
                        "⚠️ 荒らし対象がありません。\n\n"
                        "!荒らし\n"
                        "で荒らし登録してください。"
                    )

                continue


            target_name = user_names.get(
                target_user_id,
                "不明なユーザー"
            )


            # ==================================
            # LINE通知
            # ==================================

            if reply_token:

                reply_message(
                    reply_token,
                    "⚠️ 退会対象ユーザー\n\n"
                    f"👤 {target_name}\n\n"
                    "管理者がLINEグループから"
                    "退会処理してください。"
                )


            # ==================================
            # Discord通知
            # ==================================

            send_discord_kick_notification(
                target_name,
                target_user_id
            )

            continue


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
