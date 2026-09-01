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
# 荒らし検知設定
# ==========================================

# 何秒以内に
# 何人退会したら警報を出すか

KICK_DETECTION_SECONDS = 10 * 60

KICK_DETECTION_COUNT = 2


# ==========================================
# グループごとの退会履歴
# ==========================================

leave_history = {}


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
# LINE返信メッセージ
# ==========================================

def reply_message(reply_token, text):

    if not reply_token:
        return

    url = (
        f"{LINE_API}/message/reply"
    )

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
# LINEプッシュメッセージ
# ==========================================

def push_message(group_id, text):

    if not group_id:
        return

    url = (
        f"{LINE_API}/message/push"
    )

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
            "プッシュ送信エラー:",
            e
        )


# ==========================================
# ユーザー名取得
# ==========================================

def get_user_name(group_id, user_id):

    if not group_id:
        return "メンバー"

    if not user_id:
        return "メンバー"

    url = (
        f"{LINE_API}/group/"
        f"{group_id}/member/"
        f"{user_id}"
    )

    headers = {
        "Authorization": (
            f"Bearer {CHANNEL_ACCESS_TOKEN}"
        )
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
                "メンバー"
            )

        print(
            "名前取得失敗:",
            response.status_code
        )

    except Exception as e:

        print(
            "名前取得エラー:",
            e
        )

    return "メンバー"


# ==========================================
# 荒らし検知
# ==========================================

def check_mass_leave(group_id):

    if not group_id:
        return False

    now = time.time()


    # --------------------------------------
    # 初回
    # --------------------------------------

    if group_id not in leave_history:

        leave_history[group_id] = []


    # --------------------------------------
    # 10分より古い記録を削除
    # --------------------------------------

    new_history = []

    for timestamp in leave_history[group_id]:

        if (
            now - timestamp
            <= KICK_DETECTION_SECONDS
        ):

            new_history.append(
                timestamp
            )


    leave_history[group_id] = (
        new_history
    )


    # --------------------------------------
    # 今回の退会を追加
    # --------------------------------------

    leave_history[group_id].append(
        now
    )


    print(
        "退会検知数:",
        len(leave_history[group_id])
    )


    # --------------------------------------
    # 2人以上なら荒らし警報
    # --------------------------------------

    if (
        len(leave_history[group_id])
        >= KICK_DETECTION_COUNT
    ):

        # 警報後にリセット

        leave_history[group_id] = []

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


    # ======================================
    # LINE署名
    # ======================================

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
    # JSON読み込み
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


    # ======================================
    # イベント取得
    # ======================================

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
                "メンバー追加イベント"
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


                name = get_user_name(
                    group_id,
                    user_id
                )


                message = (
                    "🟢 メンバー追加\n\n"
                    f"👤 {name}さんが\n"
                    "グループに追加されました。"
                )


                # memberJoinedは
                # replyTokenがあるため返信

                if reply_token:

                    reply_message(
                        reply_token,
                        message
                    )


        # ==================================
        # メンバー退会
        # ==================================

        elif event_type == "memberLeft":

            print(
                "⚠️ メンバー退会イベント"
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
                    "退会ユーザー:",
                    user_id
                )


                # ==================================
                # 退会通知
                # ==================================

                message = (
                    "🛡️ 蹴り保護Bot\n\n"
                    "⚠️ メンバーの退会を検知しました。\n\n"
                    "🚨 グループからメンバーが\n"
                    "退出・削除された可能性があります。\n\n"
                    "※LINEの仕様上、\n"
                    "誰が削除したかは\n"
                    "Botから判別できません。"
                )


                # ==================================
                # ★重要★
                # memberLeftはPush送信
                # ==================================

                push_message(
                    group_id,
                    message
                )


                # ==================================
                # 荒らし検知
                # ==================================

                is_mass_leave = (
                    check_mass_leave(
                        group_id
                    )
                )


                if is_mass_leave:

                    print(
                        "🚨 荒らし警報発動"
                    )


                    alert_message = (
                        "🚨🚨 荒らし警報 🚨🚨\n\n"
                        "⚠️ 10分以内に\n"
                        "2人以上のメンバーの\n"
                        "退会を検知しました。\n\n"
                        "🛡️ 蹴り・荒らし行為の\n"
                        "可能性があります。\n\n"
                        "👑 管理者はグループを\n"
                        "確認してください。\n\n"
                        "※LINEの仕様上、\n"
                        "誰が削除したかは\n"
                        "Botから判別できません。"
                    )


                    push_message(
                        group_id,
                        alert_message
                    )


        # ==================================
        # 通常メッセージ
        # ==================================

        elif event_type == "message":

            print(
                "通常メッセージを受信しました"
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
    # LINEへ200を返す
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
