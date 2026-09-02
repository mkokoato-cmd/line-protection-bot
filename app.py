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
# 管理者設定
#
# Renderの環境変数に
# ADMIN_USER_IDS
# を設定してください。
#
# 複数人の場合
# userID1,userID2,userID3
# ==========================================

ADMIN_USER_IDS = os.environ.get(
    "ADMIN_USER_IDS",
    ""
)

ADMIN_USER_IDS = [
    x.strip()
    for x in ADMIN_USER_IDS.split(",")
    if x.strip()
]


# ==========================================
# スパム設定
# ==========================================

# ★ 荒らし回数2回
SPAM_COUNT = 2

# ★ 10秒以内
SPAM_WINDOW = 10


# ==========================================
# 荒らし自動検知設定
# ==========================================

# グループごとのON/OFF
spam_settings = {}


# ==========================================
# 荒らし対象者
#
# group_id:
#   user_id:
#       name
#       count
#       detected_at
# ==========================================

spam_targets = {}


# ==========================================
# 最後に検知した荒らし
#
# /追い出し
# で使用
# ==========================================

last_spammer = {}


# ==========================================
# 追い出し検知設定
# ==========================================

KICK_WINDOW = 60


# ==========================================
# メモリ保存
# ==========================================

users = {}

# group_idごとの削除履歴
kick_records = {}


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
        return False

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

        return response.status_code == 200

    except Exception as e:

        print(
            "LINE reply error:",
            e
        )

        return False


# ==========================================
# LINEプッシュ送信
# ==========================================

def push_message(group_id, text):

    if not group_id:
        return False

    url = f"{LINE_API}/message/push"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
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
            response.status_code,
            response.text
        )

        return response.status_code == 200

    except Exception as e:

        print(
            "LINE push error:",
            e
        )

        return False


# ==========================================
# Discord通知
# ==========================================

def send_discord(message):

    if not DISCORD_WEBHOOK_URL:
        print("Discord webhook not configured")
        return False

    data = {
        "content": message
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

        return response.status_code in [200, 204]

    except Exception as e:

        print(
            "Discord error:",
            e
        )

        return False


# ==========================================
# 管理者チェック
# ==========================================

def is_admin(user_id):

    if not user_id:
        return False

    return user_id in ADMIN_USER_IDS


# ==========================================
# ユーザープロフィール取得
# ==========================================

def get_user_profile(group_id, user_id):

    if not user_id:
        return None

    if not group_id:
        return None

    url = f"{LINE_API}/group/{group_id}/member/{user_id}"

    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        print(
            "PROFILE:",
            response.status_code,
            response.text
        )

        if response.status_code == 200:

            return response.json()

    except Exception as e:

        print(
            "Profile error:",
            e
        )

    return None


# ==========================================
# グループ名取得
# ==========================================

def get_group_name(group_id):

    if not group_id:
        return "不明"

    url = f"{LINE_API}/group/{group_id}/summary"

    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        print(
            "GROUP:",
            response.status_code,
            response.text
        )

        if response.status_code == 200:

            data = response.json()

            return data.get(
                "groupName",
                "不明"
            )

    except Exception as e:

        print(
            "Group error:",
            e
        )

    return "不明"


# ==========================================
# 削除人数を記録
# ==========================================

def register_kick(group_id, count):

    now = time.time()

    if group_id not in kick_records:
        kick_records[group_id] = []

    kick_records[group_id] = [
        t
        for t in kick_records[group_id]
        if now - t < KICK_WINDOW
    ]

    for _ in range(count):
        kick_records[group_id].append(now)

    return len(kick_records[group_id])


# ==========================================
# メンバー名取得
# ==========================================

def get_member_names(group_id, members):

    names = []

    for member in members:

        user_id = member.get("userId")

        if not user_id:
            continue

        name = None

        if user_id in users:

            name = users[user_id].get(
                "name"
            )

        if not name:

            profile = get_user_profile(
                group_id,
                user_id
            )

            if profile:

                name = profile.get(
                    "displayName"
                )

        if not name:
            name = "名前取得不可"

        users[user_id] = {
            "name": name
        }

        names.append(name)

    return names


# ==========================================
# 荒らし設定取得
# ==========================================

def is_spam_enabled(group_id):

    if not group_id:
        return False

    return spam_settings.get(
        group_id,
        True
    )


# ==========================================
# 荒らし設定ON
# ==========================================

def enable_spam(group_id):

    spam_settings[group_id] = True


# ==========================================
# 荒らし設定OFF
# ==========================================

def disable_spam(group_id):

    spam_settings[group_id] = False


# ==========================================
# 荒らし対象登録
# ==========================================

def register_spam_target(
    group_id,
    user_id,
    name,
    count
):

    if group_id not in spam_targets:

        spam_targets[group_id] = {}

    spam_targets[group_id][user_id] = {

        "name": name,

        "count": count,

        "detected_at": time.time()
    }

    last_spammer[group_id] = {

        "user_id": user_id,

        "name": name,

        "detected_at": time.time()
    }


# ==========================================
# 荒らし対象取得
# ==========================================

def get_spam_target(group_id, user_id):

    if group_id not in spam_targets:
        return None

    return spam_targets[group_id].get(
        user_id
    )


# ==========================================
# トップページ
# ==========================================

@app.route("/", methods=["GET"])
def home():

    return "LINE Protection Bot is running!"


# ==========================================
# Webhook
# ==========================================

@app.route("/callback", methods=["POST"])
def callback():

    body = request.get_data()

    signature = request.headers.get(
        "X-Line-Signature"
    )

    print("================================")
    print("Webhook received")
    print("================================")


    # ======================================
    # 署名チェック
    # ======================================

    if not verify_signature(
        body,
        signature
    ):

        print("Invalid signature")

        abort(400)


    # ======================================
    # JSON解析
    # ======================================

    try:

        data = json.loads(
            body.decode("utf-8")
        )

    except Exception as e:

        print(
            "JSON error:",
            e
        )

        abort(400)


    events = data.get(
        "events",
        []
    )


    print(
        "EVENT COUNT:",
        len(events)
    )


    # ======================================
    # イベント処理
    # ======================================

    for event in events:

        try:

            event_type = event.get(
                "type"
            )

            print(
                "EVENT TYPE:",
                event_type
            )


            # ==================================
            # メッセージ
            # ==================================

            if event_type == "message":

                message = event.get(
                    "message",
                    {}
                )

                if message.get("type") != "text":
                    continue

                text = message.get(
                    "text",
                    ""
                ).strip()

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

                if not user_id:
                    continue


                # ==================================
                # 管理者コマンド
                # ==================================

                if text in [
                    "/荒らし設定 ON",
                    "/荒らし設定ON"
                ]:

                    if not group_id:
                        continue

                    if not is_admin(user_id):

                        reply_message(
                            reply_token,
                            "⛔ このコマンドは管理者専用です。"
                        )

                        continue

                    enable_spam(group_id)

                    message_text = (
                        "🛡️ 荒らし自動検知設定\n\n"
                        "✅ ONにしました。\n\n"
                        "🚨 荒らし判定：2回\n"
                        f"⏱ 判定時間：{SPAM_WINDOW}秒以内\n\n"
                        "同じ人が2回連投すると\n"
                        "荒らし対象として記録します。"
                    )

                    reply_message(
                        reply_token,
                        message_text
                    )

                    send_discord(
                        message_text
                    )

                    continue


                if text in [
                    "/荒らし設定 OFF",
                    "/荒らし設定OFF"
                ]:

                    if not group_id:
                        continue

                    if not is_admin(user_id):

                        reply_message(
                            reply_token,
                            "⛔ このコマンドは管理者専用です。"
                        )

                        continue

                    disable_spam(group_id)

                    message_text = (
                        "🛡️ 荒らし自動検知設定\n\n"
                        "❌ OFFにしました。\n\n"
                        "荒らし自動検知を停止しました。"
                    )

                    reply_message(
                        reply_token,
                        message_text
                    )

                    send_discord(
                        message_text
                    )

                    continue


                # ==================================
                # 強制追い出し対象コマンド
                #
                # /追い出し
                #
                # 最後に検知した荒らしを
                # 追い出し対象として通知
                # ==================================

                if text == "/追い出し":

                    if not group_id:
                        continue

                    if not is_admin(user_id):

                        reply_message(
                            reply_token,
                            "⛔ このコマンドは管理者専用です。"
                        )

                        continue

                    target = last_spammer.get(
                        group_id
                    )

                    if not target:

                        reply_message(
                            reply_token,
                            "ℹ️ 現在、追い出し対象として記録された荒らしはいません。"
                        )

                        continue

                    target_user_id = target.get(
                        "user_id"
                    )

                    target_name = target.get(
                        "name",
                        "不明"
                    )

                    group_name = get_group_name(
                        group_id
                    )

                    kick_message = (
                        "🚨 荒らし強制追い出し対象\n\n"
                        f"👤 ユーザー：{target_name}\n"
                        f"🆔 ユーザーID：{target_user_id}\n"
                        f"👥 グループ：{group_name}\n\n"
                        "⚠️ このユーザーを強制退会させてください。\n"
                        "※ LINE Botから他メンバーを直接退会させることはできません。\n\n"
                        "🛡️ グループ保護Bot"
                    )

                    reply_message(
                        reply_token,
                        kick_message
                    )

                    send_discord(
                        kick_message
                    )

                    continue


                # ==================================
                # 荒らし対象確認
                # ==================================

                if text == "/荒らし対象":

                    if not group_id:
                        continue

                    if not is_admin(user_id):

                        reply_message(
                            reply_token,
                            "⛔ このコマンドは管理者専用です。"
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
                        "🚨 荒らし対象一覧",
                        ""
                    ]

                    for target_id, target in targets.items():

                        lines.append(
                            f"👤 {target.get('name', '不明')}"
                        )

                        lines.append(
                            f"🆔 {target_id}"
                        )

                        lines.append(
                            f"💬 {target.get('count', 0)}回"
                        )

                        lines.append("")

                    reply_message(
                        reply_token,
                        "\n".join(lines)
                    )

                    continue


                # ==================================
                # 名前取得
                # ==================================

                name = "不明"

                if group_id:

                    profile = get_user_profile(
                        group_id,
                        user_id
                    )

                    if profile:

                        name = profile.get(
                            "displayName",
                            "不明"
                        )


                # ==================================
                # ユーザー保存
                # ==================================

                if user_id not in users:

                    users[user_id] = {

                        "name": name,

                        "messages": []
                    }

                users[user_id]["name"] = name

                if "messages" not in users[user_id]:

                    users[user_id]["messages"] = []


                # ==================================
                # 荒らし検知OFFなら終了
                # ==================================

                if not group_id:
                    continue

                if not is_spam_enabled(group_id):
                    continue


                # ==================================
                # メッセージ時間保存
                # ==================================

                now = time.time()

                users[user_id]["messages"].append(
                    now
                )


                # ==================================
                # 10秒より古いもの削除
                # ==================================

                users[user_id]["messages"] = [

                    t

                    for t in users[user_id]["messages"]

                    if now - t <= SPAM_WINDOW
                ]


                message_count = len(
                    users[user_id]["messages"]
                )


                print(
                    "SPAM CHECK:",
                    name,
                    message_count
                )


                # ==================================
                # 2回で荒らし判定
                # ==================================

                if message_count >= SPAM_COUNT:

                    group_name = get_group_name(
                        group_id
                    )


                    # ==================================
                    # 荒らし対象登録
                    # ==================================

                    register_spam_target(

                        group_id,

                        user_id,

                        name,

                        message_count
                    )


                    # ==================================
                    # 警告
                    # ==================================

                    warning = (

                        "🚨 荒らしを検知しました\n\n"

                        f"👤 ユーザー：{name}\n"

                        f"🆔 ユーザーID：{user_id}\n"

                        f"👥 グループ：{group_name}\n"

                        f"💬 連投：{message_count}回\n"

                        f"⏱ 判定時間：{SPAM_WINDOW}秒以内\n\n"

                        "⚠️ このユーザーを\n"
                        "強制追い出し対象として記録しました。\n\n"

                        "管理者は\n"
                        "「/追い出し」\n"
                        "を使用してください。\n\n"

                        "🛡️ グループ保護Bot監視中"
                    )


                    # ==================================
                    # LINE返信
                    # ==================================

                    if reply_token:

                        reply_message(

                            reply_token,

                            warning
                        )


                    # ==================================
                    # Discord
                    # ==================================

                    send_discord(
                        warning
                    )


                    # ==================================
                    # カウントリセット
                    # ==================================

                    users[user_id]["messages"] = []


            # ==================================
            # メンバー追加
            # ==================================

            elif event_type == "memberJoined":

                source = event.get(
                    "source",
                    {}
                )

                group_id = source.get(
                    "groupId"
                )

                if not group_id:
                    continue

                members = event.get(
                    "joined",
                    {}
                ).get(
                    "members",
                    []
                )

                names = get_member_names(
                    group_id,
                    members
                )

                if not names:

                    names = [
                        "名前取得不可"
                    ]

                group_name = get_group_name(
                    group_id
                )

                member_text = "\n".join(
                    [
                        f"👤 {name}"
                        for name in names
                    ]
                )

                notification = (

                    "✅ メンバー追加を検知しました\n\n"

                    f"👥 グループ：{group_name}\n"

                    f"{member_text}\n\n"

                    "🛡️ グループ保護Bot監視中"
                )

                print(
                    notification
                )

                reply_token = event.get(
                    "replyToken"
                )

                if reply_token:

                    reply_message(
                        reply_token,
                        notification
                    )

                send_discord(
                    notification
                )


            # ==================================
            # メンバー削除
            # ==================================

            elif event_type == "memberLeft":

                source = event.get(
                    "source",
                    {}
                )

                group_id = source.get(
                    "groupId"
                )

                if not group_id:
                    continue

                members = event.get(
                    "left",
                    {}
                ).get(
                    "members",
                    []
                )


                # ==================================
                # 削除人数
                # ==================================

                count = len(members)

                if count <= 0:
                    count = 1


                # ==================================
                # 名前取得
                # ==================================

                names = get_member_names(
                    group_id,
                    members
                )

                if not names:

                    names = [
                        "名前取得不可"
                    ]


                # ==================================
                # 削除記録
                # ==================================

                total_kicks = register_kick(
                    group_id,
                    count
                )


                # ==================================
                # グループ名
                # ==================================

                group_name = get_group_name(
                    group_id
                )


                # ==================================
                # 名前表示
                # ==================================

                member_text = "\n".join(
                    [
                        f"👤 {name}"
                        for name in names
                    ]
                )


                # ==================================
                # 警告
                # ==================================

                notification = (

                    "🚨 メンバー削除を検知しました\n\n"

                    f"👥 グループ：{group_name}\n"

                    f"{member_text}\n\n"

                    f"⚠️ 今回の削除人数：{count}人\n"

                    f"📊 直近{KICK_WINDOW}秒の削除人数：{total_kicks}人\n\n"

                    "⚠️ 管理者は確認してください。\n"

                    "🛡️ グループ保護Bot監視中"
                )

                print(
                    notification
                )


                # ==================================
                # LINE Push
                # ==================================

                push_message(
                    group_id,
                    notification
                )


                # ==================================
                # Discord
                # ==================================

                send_discord(
                    notification
                )


        except Exception as e:

            print(
                "EVENT ERROR:",
                repr(e)
            )

            continue


    # ======================================
    # LINEには必ず200
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
