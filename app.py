import os
import json
import hmac
import hashlib
import base64
import time

from flask import Flask, request, abort
import requests


app = Flask(__name__)


# ==========================================
# LINE設定
# ==========================================

CHANNEL_SECRET = os.environ.get(
    "CHANNEL_SECRET"
)

CHANNEL_ACCESS_TOKEN = os.environ.get(
    "CHANNEL_ACCESS_TOKEN"
)

LINE_API = "https://api.line.me/v2/bot"


# ==========================================
# Discord設定
# ==========================================

DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL"
)


# ==========================================
# 荒らし検知設定
# ==========================================

# 10分以内に
# 別々の2人以上の退会を検知したら警報

DETECTION_TIME = 10 * 60
DETECTION_COUNT = 2


# ==========================================
# スパム検知設定
# ==========================================

# 同じ人が30秒以内に
# 同じ内容を5回以上送信したら警告

SPAM_TIME = 30
SPAM_COUNT = 5


# ==========================================
# グループごとの退会履歴
# ==========================================

leave_history = {}


# ==========================================
# グループごとのスパム履歴
# ==========================================

spam_history = {}


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
            response.status_code
        )

        print(
            response.text
        )

    except Exception as e:

        print(
            "返信エラー:",
            e
        )


# ==========================================
# LINE Push
# ==========================================

def push_message(group_id, text):

    if not group_id:
        return

    if not CHANNEL_ACCESS_TOKEN:
        return

    url = f"{LINE_API}/message/push"

    headers = {
        "Content-Type": "application/json",
        "Authorization": (
            f"Bearer {CHANNEL_ACCESS_TOKEN}"
        )
    }

    data = {
        "to": group_id,
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
            "LINE push:",
            response.status_code
        )

        print(
            response.text
        )

    except Exception as e:

        print(
            "Push送信エラー:",
            e
        )


# ==========================================
# Discord通知
# ==========================================

def discord_message(text):

    if not DISCORD_WEBHOOK_URL:
        print(
            "Discord Webhook URLが設定されていません"
        )
        return

    data = {
        "content": text
    }

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=data,
            timeout=10
        )

        print(
            "Discord通知:",
            response.status_code
        )

        print(
            response.text
        )

    except Exception as e:

        print(
            "Discord通知エラー:",
            e
        )


# ==========================================
# 荒らし検知
# ==========================================

def check_leave(group_id, user_id):

    if not group_id:
        return False

    if not user_id:
        return False

    now = time.time()

    # --------------------------------------
    # グループ初回
    # --------------------------------------

    if group_id not in leave_history:

        leave_history[group_id] = []

    # --------------------------------------
    # 古い記録を削除
    # --------------------------------------

    leave_history[group_id] = [

        item

        for item in leave_history[group_id]

        if now - item["time"] <= DETECTION_TIME
    ]

    # --------------------------------------
    # 同じ人がすでに記録されているか
    # --------------------------------------

    already_recorded = any(

        item["user_id"] == user_id

        for item in leave_history[group_id]
    )

    # --------------------------------------
    # 同じ人なら重複カウントしない
    # --------------------------------------

    if already_recorded:

        print(
            "同じユーザーなので重複カウントしません"
        )

        return False

    # --------------------------------------
    # 今回の退会を記録
    # --------------------------------------

    leave_history[group_id].append(
        {
            "user_id": user_id,
            "time": now
        }
    )

    print(
        "現在の別ユーザー退会人数:",
        len(leave_history[group_id])
    )

    # --------------------------------------
    # 2人以上なら警報
    # --------------------------------------

    if len(leave_history[group_id]) >= DETECTION_COUNT:

        print(
            "🚨 荒らし警報発動"
        )

        leave_history[group_id] = []

        return True

    return False


# ==========================================
# スパム検知
# ==========================================

def check_spam(group_id, user_id, text):

    if not group_id:
        return False

    if not user_id:
        return False

    if not text:
        return False

    now = time.time()

    # --------------------------------------
    # グループ初回
    # --------------------------------------

    if group_id not in spam_history:

        spam_history[group_id] = {}

    # --------------------------------------
    # ユーザー初回
    # --------------------------------------

    if user_id not in spam_history[group_id]:

        spam_history[group_id][user_id] = []

    # --------------------------------------
    # 古い記録を削除
    # --------------------------------------

    spam_history[group_id][user_id] = [

        item

        for item in spam_history[group_id][user_id]

        if now - item["time"] <= SPAM_TIME
    ]

    # --------------------------------------
    # 今回のメッセージを記録
    # --------------------------------------

    spam_history[group_id][user_id].append(
        {
            "text": text,
            "time": now
        }
    )

    # --------------------------------------
    # 同じ内容だけ取り出す
    # --------------------------------------

    same_messages = [

        item

        for item in spam_history[group_id][user_id]

        if item["text"] == text
    ]

    print(
        "同じ内容の送信回数:",
        len(same_messages)
    )

    # --------------------------------------
    # 5回以上ならスパム
    # --------------------------------------

    if len(same_messages) >= SPAM_COUNT:

        spam_history[group_id][user_id] = []

        return True

    return False


# ==========================================
# Webhook
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

        print(
            "署名チェック失敗"
        )

        abort(400)

    # ======================================
    # JSON
    # ======================================

    try:

        data = json.loads(
            body.decode("utf-8")
        )

    except Exception as e:

        print(
            "JSONエラー:",
            e
        )

        abort(400)

    events = data.get(
        "events",
        []
    )

    print(
        "受信イベント:",
        events
    )

    # ======================================
    # イベント処理
    # ======================================

    for event in events:

        event_type = event.get(
            "type"
        )

        reply_token = event.get(
            "replyToken"
        )

        source = event.get(
            "source",
            {}
        )

        group_id = source.get(
            "groupId"
        )

        # ==================================
        # メンバー追加
        # ==================================

        if event_type == "memberJoined":

            print(
                "🟢 メンバー追加検知"
            )

            joined = event.get(
                "joined",
                {}
            )

            members = joined.get(
                "members",
                []
            )

            for member in members:

                user_id = member.get(
                    "userId"
                )

                if not user_id:
                    continue

                message = (
                    "🟢 メンバー追加\n\n"
                    "👤 新しいメンバーが\n"
                    "グループに追加されました。"
                )

                push_message(
                    group_id,
                    message
                )

                discord_message(
                    "🟢 **メンバー追加検知**\n"
                    "LINEグループに新しいメンバーが追加されました。"
                )

        # ==================================
        # メンバー退会・削除
        # ==================================

        elif event_type == "memberLeft":

            print(
                "🛡️ メンバー退会検知"
            )

            left = event.get(
                "left",
                {}
            )

            members = left.get(
                "members",
                []
            )

            for member in members:

                user_id = member.get(
                    "userId"
                )

                if not user_id:
                    continue

                print(
                    "退出ユーザーID:",
                    user_id
                )

                # ==========================
                # 退会通知
                # ==========================

                leave_message = (
                    "🛡️ 蹴り保護Bot\n\n"
                    "🔴 メンバーの退会を検知しました。\n\n"
                    "👤 グループからメンバーが\n"
                    "退出・削除された可能性があります。\n\n"
                    "⚠️ LINEの仕様上、\n"
                    "誰が削除したかは\n"
                    "自動判定できません。"
                )

                # ==========================
                # LINE通知
                # ==========================

                push_message(
                    group_id,
                    leave_message
                )

                # ==========================
                # Discord通知
                # ==========================

                discord_message(
                    "🔴 **メンバー退会検知**\n\n"
                    "LINEグループでメンバーの退会・削除を検知しました。\n\n"
                    "⚠️ 誰が削除したかはLINEの仕様上、"
                    "Botから特定できません。"
                )

                # ==========================
                # 荒らし判定
                # ==========================

                detected = check_leave(
                    group_id,
                    user_id
                )

                if detected:

                    print(
                        "🚨 荒らし警報発動"
                    )

                    alert_message = (
                        "🚨🚨 荒らし警報 🚨🚨\n\n"
                        "⚠️ 10分以内に\n"
                        "別々の2人以上のメンバーの\n"
                        "退会・削除を検知しました。\n\n"
                        "🛡️ 蹴り・荒らし行為の\n"
                        "可能性があります。\n\n"
                        "👑 管理者はグループを\n"
                        "確認してください。\n\n"
                        "⚠️ LINEの仕様上、\n"
                        "誰が削除したかは\n"
                        "Botから特定できません。"
                    )

                    # LINE警報

                    push_message(
                        group_id,
                        alert_message
                    )

                    # Discord警報

                    discord_message(
                        "🚨🚨 **荒らし警報** 🚨🚨\n\n"
                        "⚠️ 10分以内に別々の2人以上の"
                        "メンバーの退会・削除を検知しました。\n\n"
                        "🛡️ 蹴り・荒らし行為の可能性があります。\n\n"
                        "⚠️ LINEの仕様上、誰が削除したかは"
                        "Botから特定できません。"
                    )

        # ==================================
        # 通常メッセージ
        # ==================================

        elif event_type == "message":

            print(
                "通常メッセージを受信しました"
            )

            message = event.get(
                "message",
                {}
            )

            message_type = message.get(
                "type"
            )

            # ==============================
            # テキストのみ
            # ==============================

            if message_type == "text":

                text = message.get(
                    "text",
                    ""
                )

                user_id = source.get(
                    "userId"
                )

                print(
                    "メッセージ:",
                    text
                )

                # ==========================
                # スパムチェック
                # ==========================

                detected = check_spam(
                    group_id,
                    user_id,
                    text
                )

                if detected:

                    print(
                        "🚨 スパム検知"
                    )

                    spam_message = (
                        "🚨 スパム検知 🚨\n\n"
                        "⚠️ 同じユーザーから\n"
                        "短時間に同じ内容の\n"
                        "連続送信を検知しました。\n\n"
                        "🛡️ 荒らし・スパムの\n"
                        "可能性があります。\n\n"
                        "👑 管理者は確認してください。"
                    )

                    # LINE通知

                    push_message(
                        group_id,
                        spam_message
                    )

                    # Discord通知

                    discord_message(
                        "🚨 **スパム検知** 🚨\n\n"
                        "同じユーザーから短時間に"
                        "同じ内容の連続送信を検知しました。\n\n"
                        "🛡️ 荒らし・スパムの可能性があります。"
                    )

        # ==================================
        # その他
        # ==================================

        else:

            print(
                "その他のイベント:",
                event_type
            )

    # ======================================
    # LINEへ200
    # ======================================

    return "OK", 200


# ==========================================
# Render起動
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
