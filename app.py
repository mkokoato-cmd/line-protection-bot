import os
import json
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
# 荒らし対策設定
# ==========================================

# 何回連続したらスパムと判定するか
SPAM_LIMIT = 5

# 何秒以内の連投を数えるか
SPAM_WINDOW = 10


# ==========================================
# ユーザー記録
# ==========================================

# {
#   "LINEユーザーID": {
#       "name": "名前",
#       "messages": [時刻, 時刻, ...]
#   }
# }
users = {}


# ==========================================
# LINE署名チェック
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

    if not reply_token:
        return

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
        requests.post(
            f"{LINE_API}/message/reply",
            headers=headers,
            json=data,
            timeout=10
        )

    except Exception as e:
        print("LINE返信エラー:", e)


# ==========================================
# LINEユーザーのプロフィール取得
# ==========================================

def get_user_profile(group_id, user_id):

    if not group_id or not user_id:
        return None

    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

    url = (
        f"{LINE_API}/group/"
        f"{group_id}/member/{user_id}"
    )

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:

            data = response.json()

            return data

        print(
            "プロフィール取得失敗:",
            response.status_code,
            response.text
        )

    except Exception as e:

        print(
            "プロフィール取得エラー:",
            e
        )

    return None


# ==========================================
# グループ名取得
# ==========================================

def get_group_name(group_id):

    if not group_id:
        return "不明なグループ"

    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

    url = (
        f"{LINE_API}/group/"
        f"{group_id}/summary"
    )

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:

            data = response.json()

            return data.get(
                "groupName",
                "不明なグループ"
            )

    except Exception as e:

        print(
            "グループ名取得エラー:",
            e
        )

    return "不明なグループ"


# ==========================================
# Discord通知
# ==========================================

def send_discord(message):

    if not DISCORD_WEBHOOK_URL:
        print(
            "DISCORD_WEBHOOK_URL が設定されていません"
        )
        return

    data = {
        "content": message
    }

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=data,
            timeout=10
        )

        if response.status_code not in [200, 204]:

            print(
                "Discord通知失敗:",
                response.status_code,
                response.text
            )

    except Exception as e:

        print(
            "Discord通知エラー:",
            e
        )


# ==========================================
# ユーザー名を記録
# ==========================================

def save_user_name(user_id, name):

    if not user_id:
        return

    if user_id not in users:

        users[user_id] = {
            "name": name,
            "messages": []
        }

    else:

        users[user_id]["name"] = name


# ==========================================
# スパム判定
# ==========================================

def check_spam(user_id):

    now = time.time()

    if user_id not in users:

        users[user_id] = {
            "name": "不明",
            "messages": []
        }

    messages = users[user_id]["messages"]

    # 古い記録を削除
    messages[:] = [
        t for t in messages
        if now - t <= SPAM_WINDOW
    ]

    # 今回のメッセージを追加
    messages.append(now)

    # 制限回数以上ならスパム
    if len(messages) >= SPAM_LIMIT:

        # 一度通知したらリセット
        users[user_id]["messages"] = []

        return True

    return False


# ==========================================
# Webhook
# ==========================================

@app.route(
    "/webhook",
    methods=["POST"]
)
def webhook():

    body = request.get_data()

    signature = request.headers.get(
        "X-Line-Signature"
    )

    # --------------------------------------
    # 署名チェック
    # --------------------------------------

    if not verify_signature(
        body,
        signature
    ):

        print("署名チェック失敗")

        abort(400)


    # --------------------------------------
    # JSON解析
    # --------------------------------------

    try:

        data = json.loads(
            body.decode("utf-8")
        )

    except Exception:

        abort(400)


    events = data.get(
        "events",
        []
    )


    # ======================================
    # イベント処理
    # ======================================

    for event in events:

        event_type = event.get(
            "type"
        )

        source = event.get(
            "source",
            {}
        )

        source_type = source.get(
            "type"
        )

        group_id = source.get(
            "groupId"
        )

        user_id = source.get(
            "userId"
        )

        reply_token = event.get(
            "replyToken"
        )


        # ==================================
        # メッセージ
        # ==================================

        if event_type == "message":

            message = event.get(
                "message",
                {}
            )

            message_type = message.get(
                "type"
            )


            # --------------------------------
            # テキストだけ対象
            # --------------------------------

            if message_type != "text":
                continue


            text = message.get(
                "text",
                ""
            )


            # --------------------------------
            # ユーザー名取得
            # --------------------------------

            user_name = "不明"


            if group_id and user_id:

                profile = get_user_profile(
                    group_id,
                    user_id
                )

                if profile:

                    user_name = profile.get(
                        "displayName",
                        "不明"
                    )


            # 名前を保存
            save_user_name(
                user_id,
                user_name
            )


            # --------------------------------
            # スパムチェック
            # --------------------------------

            if check_spam(user_id):

                # LINE警告
                reply_message(
                    reply_token,
                    "⚠️ 荒らし・連投を検知しました。\n"
                    "連続投稿をやめてください。"
                )


                # グループ名
                group_name = get_group_name(
                    group_id
                )


                # Discord通知
                discord_message = (
                    "🚨 **スパム・荒らし検知**\n\n"
                    f"👤 ユーザー：{user_name}\n"
                    f"🆔 User ID：{user_id}\n"
                    f"👥 グループ：{group_name}\n"
                    f"💬 内容：{text[:500]}"
                )

                send_discord(
                    discord_message
                )


        # ==================================
        # メンバー追加
        # ==================================

        elif event_type == "memberJoined":

            joined = event.get(
                "joined",
                {}
            )

            members = joined.get(
                "members",
                []
            )

            group_name = get_group_name(
                group_id
            )


            for member in members:

                joined_user_id = member.get(
                    "userId"
                )

                user_name = "不明"


                # プロフィール取得
                profile = get_user_profile(
                    group_id,
                    joined_user_id
                )

                if profile:

                    user_name = profile.get(
                        "displayName",
                        "不明"
                    )


                # 名前保存
                save_user_name(
                    joined_user_id,
                    user_name
                )


                # LINE通知
                if reply_token:

                    reply_message(
                        reply_token,
                        f"👤 {user_name} さんが\n"
                        f"グループに追加されました。"
                    )


                # Discord通知
                discord_message = (
                    "🟢 **メンバー追加検知**\n\n"
                    f"👤 追加された人：{user_name}\n"
                    f"🆔 User ID：{joined_user_id}\n"
                    f"👥 グループ：{group_name}"
                )

                send_discord(
                    discord_message
                )


        # ==================================
        # メンバー退出
        # ==================================

        elif event_type == "memberLeft":

            left = event.get(
                "left",
                {}
            )

            members = left.get(
                "members",
                []
            )

            group_name = get_group_name(
                group_id
            )


            for member in members:

                left_user_id = member.get(
                    "userId"
                )


                # --------------------------------
                # まず保存していた名前を探す
                # --------------------------------

                user_name = "不明"


                if left_user_id in users:

                    user_name = users[
                        left_user_id
                    ].get(
                        "name",
                        "不明"
                    )


                # --------------------------------
                # APIでも取得を試す
                # --------------------------------

                profile = get_user_profile(
                    group_id,
                    left_user_id
                )

                if profile:

                    user_name = profile.get(
                        "displayName",
                        user_name
                    )


                # --------------------------------
                # LINEへ通知
                # --------------------------------

                if reply_token:

                    reply_message(
                        reply_token,
                        f"🚨 メンバー退出を検知\n\n"
                        f"👤 退出した人：{user_name}"
                    )


                # --------------------------------
                # Discordへ通知
                # --------------------------------

                discord_message = (
                    "🔴 **メンバー退出・追い出し検知**\n\n"
                    f"👤 退出した人：**{user_name}**\n"
                    f"🆔 User ID：{left_user_id}\n"
                    f"👥 グループ：{group_name}\n\n"
                    "⚠️ LINEの仕様上、"
                    "このイベントだけでは"
                    "「誰が追い出したか」は取得できません。"
                )


                send_discord(
                    discord_message
                )


    # ======================================
    # LINEへ正常終了を返す
    # ======================================

    return "OK", 200


# ==========================================
# ヘルスチェック
# ==========================================

@app.route("/")
def index():

    return "LINE Protection Bot is running."


# ==========================================
# Render用ポート
# ==========================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
