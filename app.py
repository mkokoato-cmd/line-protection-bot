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

DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL"
)


# ==========================================
# 管理者設定
#
# Render:
#
# KEY
# ADMIN_USER_IDS
#
# VALUE
# Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
#
# ==========================================

ADMIN_USER_IDS = [
    x.strip()
    for x in os.environ.get(
        "ADMIN_USER_IDS",
        ""
    ).split(",")
    if x.strip()
]


# ==========================================
# 荒らし検知設定
# ==========================================

SPAM_COUNT = 2
SPAM_WINDOW = 10


# ==========================================
# 退出検知
# ==========================================

KICK_WINDOW = 60


# ==========================================
# メモリ保存
# ==========================================

users = {}

spam_settings = {}

spam_targets = {}

last_spammer = {}

kick_records = {}

# 各グループの最後の通常メッセージ送信者
last_user = {}


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
        return False

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

        return response.ok

    except Exception as e:

        print(
            "LINE reply error:",
            e
        )

        return False


# ==========================================
# LINEプッシュ送信
# ==========================================

def push_message(to, text):

    if not CHANNEL_ACCESS_TOKEN:
        return False

    url = f"{LINE_API}/message/push"

    headers = {
        "Content-Type": "application/json",
        "Authorization": (
            f"Bearer {CHANNEL_ACCESS_TOKEN}"
        )
    }

    data = {
        "to": to,
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
            response.status_code,
            response.text
        )

        return response.ok

    except Exception as e:

        print(
            "LINE push error:",
            e
        )

        return False


# ==========================================
# Discord通知
# ==========================================

def send_discord(text):

    if not DISCORD_WEBHOOK_URL:
        return False

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
            "Discord:",
            response.status_code,
            response.text
        )

        return response.ok

    except Exception as e:

        print(
            "Discord error:",
            e
        )

        return False


# ==========================================
# LINEユーザープロフィール取得
# ==========================================

def get_user_profile(user_id):

    if not CHANNEL_ACCESS_TOKEN:
        return "名前不明"

    url = f"{LINE_API}/profile/{user_id}"

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

        if response.ok:

            data = response.json()

            return data.get(
                "displayName",
                "名前不明"
            )

    except Exception as e:

        print(
            "profile error:",
            e
        )

    return "名前不明"


# ==========================================
# グループ名取得
# ==========================================

def get_group_name(group_id):

    if not CHANNEL_ACCESS_TOKEN:
        return "グループ名不明"

    url = (
        f"{LINE_API}/group/"
        f"{group_id}/summary"
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

        if response.ok:

            data = response.json()

            return data.get(
                "groupName",
                "グループ名不明"
            )

    except Exception as e:

        print(
            "group name error:",
            e
        )

    return "グループ名不明"


# ==========================================
# 管理者確認
# ==========================================

def is_admin(user_id):

    if not user_id:
        return False

    return user_id in ADMIN_USER_IDS


# ==========================================
# 荒らし検知ON/OFF
# ==========================================

def is_spam_enabled(group_id):

    return spam_settings.get(
        group_id,
        True
    )


# ==========================================
# 荒らし対象登録
# ==========================================

def register_spam_target(
    group_id,
    user_id,
    user_name
):

    if group_id not in spam_targets:

        spam_targets[group_id] = {}

    spam_targets[group_id][user_id] = {
        "name": user_name,
        "user_id": user_id,
        "time": time.time()
    }

    last_spammer[group_id] = {
        "name": user_name,
        "user_id": user_id,
        "time": time.time()
    }


# ==========================================
# 退出記録
# ==========================================

def register_kick(
    group_id,
    user_id,
    user_name
):

    now = time.time()

    if group_id not in kick_records:

        kick_records[group_id] = []

    kick_records[group_id] = [
        x
        for x in kick_records[group_id]
        if now - x["time"] <= KICK_WINDOW
    ]

    kick_records[group_id].append({
        "user_id": user_id,
        "name": user_name,
        "time": now
    })

    return len(
        kick_records[group_id]
    )


# ==========================================
# メンバー名取得
# ==========================================

def get_member_names(
    group_id,
    members
):

    names = []

    for member in members:

        member_id = member.get(
            "userId"
        )

        if not member_id:
            continue

        name = get_user_profile(
            member_id
        )

        names.append({
            "user_id": member_id,
            "name": name
        })

    return names


# ==========================================
# TOP
# ==========================================

@app.route("/")
def index():

    return "LINE Protection Bot is running!"


# ==========================================
# CALLBACK
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
    # 署名確認
    # ======================================

    if not verify_signature(
        body,
        signature
    ):

        print(
            "Invalid signature"
        )

        abort(400)


    # ======================================
    # JSON
    # ======================================

    try:

        data = json.loads(
            body.decode("utf-8")
        )

    except Exception:

        abort(400)


    # ======================================
    # イベント
    # ======================================

    for event in data.get(
        "events",
        []
    ):

        event_type = event.get(
            "type"
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


            # テキスト以外は無視
            if message_type != "text":
                continue


            text = message.get(
                "text",
                ""
            ).strip()


            # ==================================
            # /ID
            #
            # LINEには返信しない
            # Discordだけに送る
            # ==================================

            if text in [
                "/ID",
                "/id",
                "ID"
            ]:

                if not is_admin(user_id):

                    # 管理者以外にも
                    # LINEには返信しない
                    continue


                if not group_id:
                    continue


                target = last_user.get(
                    group_id
                )


                if not target:

                    send_discord(
                        "⚠️ **User ID取得失敗**\n"
                        "まだ通常メッセージを送った"
                        "ユーザーがいません。"
                    )

                    continue


                # ------------------------------
                # Discordだけに送信
                # ------------------------------

                send_discord(
                    "👤 **ユーザー情報**\n"
                    f"グループ: "
                    f"{get_group_name(group_id)}\n"
                    f"名前: {target['name']}\n"
                    f"LINE User ID:\n"
                    f"{target['user_id']}"
                )


                # LINEには返信しない
                continue


            # ==================================
            # ユーザー名取得
            # ==================================

            user_name = get_user_profile(
                user_id
            )


            # ==================================
            # 荒らし設定 ON
            # ==================================

            if text in [
                "/荒らし設定 ON",
                "/荒らし設定ON",
                "/荒らし設定 on",
                "/荒らし設定on"
            ]:

                if not is_admin(user_id):

                    reply_message(
                        reply_token,
                        "⛔ このコマンドは管理者専用です。"
                    )

                    continue


                if group_id:

                    spam_settings[
                        group_id
                    ] = True


                    reply_message(
                        reply_token,
                        "🛡 荒らし検知をONにしました！"
                    )


                    send_discord(
                        "🛡 **荒らし検知 ON**\n"
                        f"グループ: "
                        f"{get_group_name(group_id)}\n"
                        f"設定者: {user_name}"
                    )

                continue


            # ==================================
            # 荒らし設定 OFF
            # ==================================

            if text in [
                "/荒らし設定 OFF",
                "/荒らし設定OFF",
                "/荒らし設定 off",
                "/荒らし設定off"
            ]:

                if not is_admin(user_id):

                    reply_message(
                        reply_token,
                        "⛔ このコマンドは管理者専用です。"
                    )

                    continue


                if group_id:

                    spam_settings[
                        group_id
                    ] = False


                    reply_message(
                        reply_token,
                        "🔕 荒らし検知をOFFにしました。"
                    )


                    send_discord(
                        "🔕 **荒らし検知 OFF**\n"
                        f"グループ: "
                        f"{get_group_name(group_id)}\n"
                        f"設定者: {user_name}"
                    )

                continue


            # ==================================
            # /荒らし対象
            # ==================================

            if text == "/荒らし対象":

                if not is_admin(user_id):

                    reply_message(
                        reply_token,
                        "⛔ このコマンドは管理者専用です。"
                    )

                    continue


                if not group_id:

                    reply_message(
                        reply_token,
                        "このコマンドはグループで使用してください。"
                    )

                    continue


                targets = spam_targets.get(
                    group_id,
                    {}
                )


                if not targets:

                    reply_message(
                        reply_token,
                        "✅ 現在、荒らし対象者はいません。"
                    )

                    continue


                lines = [
                    "🚨 荒らし対象一覧"
                ]


                for target in targets.values():

                    lines.append(
                        "\n👤 "
                        + target["name"]
                        + "\n🆔 "
                        + target["user_id"]
                    )


                reply_message(
                    reply_token,
                    "\n".join(lines)
                )

                continue


            # ==================================
            # /追い出し
            # ==================================

            if text == "/追い出し":

                if not is_admin(user_id):

                    reply_message(
                        reply_token,
                        "⛔ このコマンドは管理者専用です。"
                    )

                    continue


                if not group_id:

                    reply_message(
                        reply_token,
                        "このコマンドはグループで使用してください。"
                    )

                    continue


                target = last_spammer.get(
                    group_id
                )


                if not target:

                    reply_message(
                        reply_token,
                        "⚠️ 追い出し対象の荒らしユーザーがいません。"
                    )

                    continue


                target_name = target[
                    "name"
                ]

                target_id = target[
                    "user_id"
                ]


                reply_message(
                    reply_token,
                    "🚨 追い出し対象\n\n"
                    "👤 名前: "
                    + target_name
                    + "\n"
                    "🆔 User ID: "
                    + target_id
                    + "\n\n"
                    "⚠️ LINEの仕様上、"
                    "Botから他のメンバーを直接"
                    "退会させることはできません。\n"
                    "管理者がLINE側で退会操作してください。"
                )


                send_discord(
                    "🚨 **追い出し対象を確認**\n"
                    f"グループ: "
                    f"{get_group_name(group_id)}\n"
                    f"対象者: {target_name}\n"
                    f"User ID: {target_id}\n"
                    f"操作した管理者: {user_name}"
                )

                continue


            # ==================================
            # 通常メッセージ
            # ==================================

            if group_id and user_id:

                # ------------------------------
                # 最後の通常メッセージ送信者を記録
                # ------------------------------

                last_user[group_id] = {
                    "name": user_name,
                    "user_id": user_id,
                    "time": time.time()
                }


                # ==================================
                # 荒らし検知OFF
                # ==================================

                if not is_spam_enabled(
                    group_id
                ):

                    continue


                # ==================================
                # ユーザー記録
                # ==================================

                if user_id not in users:

                    users[user_id] = {
                        "name": user_name,
                        "messages": []
                    }


                users[user_id][
                    "name"
                ] = user_name


                now = time.time()


                # ==================================
                # 古い履歴削除
                # ==================================

                users[user_id][
                    "messages"
                ] = [
                    t
                    for t in users[user_id][
                        "messages"
                    ]
                    if now - t <= SPAM_WINDOW
                ]


                # ==================================
                # 今回のメッセージ
                # ==================================

                users[user_id][
                    "messages"
                ].append(now)


                count = len(
                    users[user_id][
                        "messages"
                    ]
                )


                print(
                    "SPAM CHECK:",
                    user_name,
                    count
                )


                # ==================================
                # 荒らし判定
                # ==================================

                if count >= SPAM_COUNT:

                    register_spam_target(
                        group_id,
                        user_id,
                        user_name
                    )


                    group_name = get_group_name(
                        group_id
                    )


                    # ------------------------------
                    # LINE警告
                    # ------------------------------

                    warning = (
                        "🚨 荒らし検知！\n\n"
                        "👤 "
                        + user_name
                        + "\n"
                        "🆔 "
                        + user_id
                        + "\n\n"
                        "⚠️ 短時間に大量の"
                        "メッセージを送信しています。\n"
                        "管理者は必要に応じて"
                        "退会処理してください。"
                    )


                    push_message(
                        group_id,
                        warning
                    )


                    # ------------------------------
                    # Discord通知
                    # ------------------------------

                    send_discord(
                        "🚨 **荒らし検知！**\n"
                        f"グループ: {group_name}\n"
                        f"ユーザー: {user_name}\n"
                        f"User ID: {user_id}\n"
                        f"判定: "
                        f"{SPAM_COUNT}回以上 / "
                        f"{SPAM_WINDOW}秒"
                    )


                    # ------------------------------
                    # カウントリセット
                    # ------------------------------

                    users[user_id][
                        "messages"
                    ] = []


        # ==================================
        # メンバー追加
        # ==================================

        elif event_type == "memberJoined":

            if not group_id:
                continue


            members = event.get(
                "joined",
                {}
            ).get(
                "members",
                []
            )


            member_names = get_member_names(
                group_id,
                members
            )


            group_name = get_group_name(
                group_id
            )


            for member in member_names:

                name = member[
                    "name"
                ]

                member_id = member[
                    "user_id"
                ]


                # ------------------------------
                # LINE通知
                # ------------------------------

                text = (
                    "👋 メンバー追加\n\n"
                    "👤 名前: "
                    + name
                    + "\n"
                    "🆔 User ID: "
                    + member_id
                )


                push_message(
                    group_id,
                    text
                )


                # ------------------------------
                # Discord通知
                # ------------------------------

                send_discord(
                    "👋 **メンバー追加**\n"
                    f"グループ: {group_name}\n"
                    f"名前: {name}\n"
                    f"User ID: {member_id}"
                )


        # ==================================
        # メンバー退出
        # ==================================

        elif event_type == "memberLeft":

            if not group_id:
                continue


            members = event.get(
                "left",
                {}
            ).get(
                "members",
                []
            )


            group_name = get_group_name(
                group_id
            )


            for member in members:

                member_id = member.get(
                    "userId"
                )


                if not member_id:
                    continue


                name = get_user_profile(
                    member_id
                )


                # ------------------------------
                # 退出記録
                # ------------------------------

                kick_count = register_kick(
                    group_id,
                    member_id,
                    name
                )


                # ------------------------------
                # LINE通知
                # ------------------------------

                text = (
                    "🚪 メンバー退出\n\n"
                    "👤 名前: "
                    + name
                    + "\n"
                    "🆔 User ID: "
                    + member_id
                )


                push_message(
                    group_id,
                    text
                )


                # ------------------------------
                # Discord通知
                # ------------------------------

                send_discord(
                    "🚪 **メンバー退出**\n"
                    f"グループ: {group_name}\n"
                    f"名前: {name}\n"
                    f"User ID: {member_id}\n"
                    f"直近{KICK_WINDOW}秒の"
                    f"退出人数: {kick_count}"
                )


    return "OK"


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
