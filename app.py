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
# スパム設定
# ==========================================

SPAM_COUNT = 5
SPAM_WINDOW = 10


# ==========================================
# 追い出し・退会検知設定
# ==========================================

KICK_WINDOW = 60


# ==========================================
# ユーザー情報
# ==========================================

users = {}


# ==========================================
# グループごとの退会人数記録
# ==========================================

kick_records = {}


# ==========================================
# LINE署名チェック
# ==========================================

def verify_signature(body, signature):

    if not signature:
        return False

    if not CHANNEL_SECRET:
        print("CHANNEL_SECRET が設定されていません")
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
        print("reply_token がありません")
        return False

    if not CHANNEL_ACCESS_TOKEN:
        print("CHANNEL_ACCESS_TOKEN が設定されていません")
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
            "LINE返信:",
            response.status_code,
            response.text
        )

        return response.status_code == 200

    except Exception as e:

        print("LINE返信エラー:", e)

        return False


# ==========================================
# Discord通知
# ==========================================

def send_discord(message):

    if not DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL が設定されていません")
        return False

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={
                "content": message
            },
            timeout=10
        )

        print(
            "Discord通知:",
            response.status_code,
            response.text
        )

        return response.status_code in [200, 204]

    except Exception as e:

        print("Discord通知エラー:", e)

        return False


# ==========================================
# ユーザープロフィール取得
# ==========================================

def get_user_profile(group_id, user_id):

    if not CHANNEL_ACCESS_TOKEN:
        return None

    url = (
        f"{LINE_API}/group/"
        f"{group_id}/member/"
        f"{user_id}"
    )

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
            "プロフィール取得:",
            response.status_code,
            response.text
        )

        if response.status_code == 200:

            return response.json()

    except Exception as e:

        print("プロフィール取得エラー:", e)

    return None


# ==========================================
# グループ名取得
# ==========================================

def get_group_name(group_id):

    if not CHANNEL_ACCESS_TOKEN:
        return "不明なグループ"

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
            "グループ情報:",
            response.status_code,
            response.text
        )

        if response.status_code == 200:

            data = response.json()

            return data.get(
                "groupName",
                "不明なグループ"
            )

    except Exception as e:

        print("グループ名取得エラー:", e)

    return "不明なグループ"


# ==========================================
# ユーザー名取得
# ==========================================

def get_member_name(group_id, user_id):

    # まず保存済みの名前を確認
    if user_id in users:

        saved_name = users[user_id].get("name")

        if saved_name:
            return saved_name

    # LINEから取得
    profile = get_user_profile(
        group_id,
        user_id
    )

    if profile:

        display_name = profile.get(
            "displayName",
            "名前不明"
        )

        users[user_id] = {
            "name": display_name,
            "messages": users.get(
                user_id,
                {}
            ).get(
                "messages",
                []
            )
        }

        return display_name

    return "名前不明"


# ==========================================
# 追い出し・退会人数を記録
# ==========================================

def register_kick(group_id, count):

    now = time.time()

    if group_id not in kick_records:

        kick_records[group_id] = []

    kick_records[group_id].append(
        {
            "time": now,
            "count": count
        }
    )

    # 60秒より古い記録を削除
    kick_records[group_id] = [
        record
        for record in kick_records[group_id]
        if now - record["time"] <= KICK_WINDOW
    ]

    total = sum(
        record["count"]
        for record in kick_records[group_id]
    )

    return total


# ==========================================
# スパム検知
# ==========================================

def check_spam(user_id):

    now = time.time()

    if user_id not in users:

        users[user_id] = {
            "name": "名前不明",
            "messages": []
        }

    if "messages" not in users[user_id]:

        users[user_id]["messages"] = []

    # 現在時刻を追加
    users[user_id]["messages"].append(now)

    # 10秒より古い記録を削除
    users[user_id]["messages"] = [
        message_time
        for message_time in users[user_id]["messages"]
        if now - message_time <= SPAM_WINDOW
    ]

    count = len(
        users[user_id]["messages"]
    )

    print(
        f"スパムチェック: "
        f"user={user_id} "
        f"count={count}"
    )

    return count >= SPAM_COUNT


# ==========================================
# テスト用トップページ
# ==========================================

@app.route("/", methods=["GET"])
def home():

    return "LINE Protection Bot is running!"


# ==========================================
# LINE Webhook
# ★ここが重要
# ==========================================

@app.route("/callback", methods=["POST"])
def callback():

    print("================================")
    print("LINE Webhookを受信しました")
    print("================================")

    body = request.get_data()

    signature = request.headers.get(
        "X-Line-Signature"
    )

    # --------------------------------------
    # 署名確認
    # --------------------------------------

    if not verify_signature(
        body,
        signature
    ):

        print("署名確認失敗")

        abort(400)

    print("署名確認OK")

    # --------------------------------------
    # JSON解析
    # --------------------------------------

    try:

        data = json.loads(
            body.decode("utf-8")
        )

    except Exception as e:

        print("JSON解析エラー:", e)

        abort(400)

    print(
        "受信データ:",
        json.dumps(
            data,
            ensure_ascii=False
        )
    )

    # --------------------------------------
    # イベント処理
    # --------------------------------------

    events = data.get(
        "events",
        []
    )

    for event in events:

        try:

            event_type = event.get(
                "type"
            )

            print(
                "イベント:",
                event_type
            )

            # ==================================
            # メッセージ
            # ==================================

            if event_type == "message":

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

                # 名前取得
                user_name = "名前不明"

                if group_id:

                    user_name = get_member_name(
                        group_id,
                        user_id
                    )

                else:

                    profile = get_user_profile(
                        group_id,
                        user_id
                    ) if group_id else None

                    if profile:

                        user_name = profile.get(
                            "displayName",
                            "名前不明"
                        )

                # 保存
                if user_id not in users:

                    users[user_id] = {
                        "name": user_name,
                        "messages": []
                    }

                else:

                    users[user_id]["name"] = user_name

                # テキストメッセージだけ処理
                message = event.get(
                    "message",
                    {}
                )

                if message.get(
                    "type"
                ) != "text":

                    continue

                text = message.get(
                    "text",
                    ""
                )

                print(
                    f"メッセージ: "
                    f"{user_name}: "
                    f"{text}"
                )

                # スパムチェック
                is_spam = check_spam(
                    user_id
                )

                if is_spam:

                    group_name = (
                        get_group_name(group_id)
                        if group_id
                        else "個人チャット"
                    )

                    warning = (
                        "⚠️ 荒らし検知\n\n"
                        f"👤 名前：{user_name}\n"
                        f"💬 連投："
                        f"{SPAM_COUNT}回以上\n"
                        f"⏱️ 判定時間："
                        f"{SPAM_WINDOW}秒以内\n\n"
                        "⚠️ 管理者は確認してください。"
                    )

                    # LINEへ返信
                    reply_message(
                        reply_token,
                        warning
                    )

                    # Discord通知
                    discord_message = (
                        "🚨 **荒らし検知**\n\n"
                        f"👥 グループ：{group_name}\n"
                        f"👤 名前：{user_name}\n"
                        f"💬 内容：{text}\n"
                        f"⚠️ {SPAM_COUNT}回以上/"
                        f"{SPAM_WINDOW}秒以内"
                    )

                    send_discord(
                        discord_message
                    )

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

                reply_token = event.get(
                    "replyToken"
                )

                joined = event.get(
                    "joined",
                    {}
                )

                members = joined.get(
                    "members",
                    []
                )

                print(
                    "メンバー追加:",
                    members
                )

                if not group_id:

                    continue

                group_name = get_group_name(
                    group_id
                )

                names = []

                for member in members:

                    user_id = member.get(
                        "userId"
                    )

                    if not user_id:

                        continue

                    name = get_member_name(
                        group_id,
                        user_id
                    )

                    names.append(name)

                if names:

                    joined_names = "\n".join(
                        f"👤 {name}"
                        for name in names
                    )

                    message = (
                        "✅ メンバー追加を検知しました\n\n"
                        f"👥 グループ：{group_name}\n\n"
                        f"{joined_names}\n\n"
                        "🛡️ グループ保護Bot監視中"
                    )

                    # LINEへ返信
                    reply_message(
                        reply_token,
                        message
                    )

                    # Discord通知
                    discord_message = (
                        "✅ **メンバー追加**\n\n"
                        f"👥 グループ：{group_name}\n\n"
                        f"{joined_names}"
                    )

                    send_discord(
                        discord_message
                    )

            # ==================================
            # メンバー退出・追い出し
            # ==================================

            elif event_type == "memberLeft":

                source = event.get(
                    "source",
                    {}
                )

                group_id = source.get(
                    "groupId"
                )

                reply_token = event.get(
                    "replyToken"
                )

                left = event.get(
                    "left",
                    {}
                )

                members = left.get(
                    "members",
                    []
                )

                print(
                    "メンバー退出:",
                    members
                )

                if not group_id:

                    continue

                group_name = get_group_name(
                    group_id
                )

                names = []

                for member in members:

                    user_id = member.get(
                        "userId"
                    )

                    if not user_id:

                        continue

                    name = get_member_name(
                        group_id,
                        user_id
                    )

                    names.append(name)

                # 退出人数
                count = len(members)

                if count == 0:

                    continue

                # 60秒以内の累計
                total_kicks = register_kick(
                    group_id,
                    count
                )

                if names:

                    left_names = "\n".join(
                        f"👤 {name}"
                        for name in names
                    )

                else:

                    left_names = "名前不明"

                # ----------------------------------
                # LINE警告
                # ----------------------------------

                warning = (
                    "⚠️ メンバー退出を検知しました\n\n"
                    f"👥 グループ：{group_name}\n\n"
                    f"{left_names}\n\n"
                    f"🚨 退出人数：{count}人\n"
                    f"⏱️ 直近60秒："
                    f"{total_kicks}人\n\n"
                    "⚠️ 荒らしによる強制退会の"
                    "可能性があります。\n"
                    "管理者は確認してください。\n\n"
                    "※LINEの仕様上、"
                    "誰が追い出したかは"
                    "取得できません。"
                )

                # LINEへ返信
                reply_message(
                    reply_token,
                    warning
                )

                # ----------------------------------
                # Discord通知
                # ----------------------------------

                discord_message = (
                    "🚨 **メンバー退出検知**\n\n"
                    f"👥 グループ：{group_name}\n\n"
                    f"{left_names}\n\n"
                    f"🚨 退出人数：{count}人\n"
                    f"⏱️ 直近60秒："
                    f"{total_kicks}人\n\n"
                    "⚠️ 荒らしによる"
                    "強制退会の可能性あり\n"
                    "実行者：不明"
                )

                send_discord(
                    discord_message
                )

        except Exception as e:

            print(
                "イベント処理エラー:",
                e
            )

    # ==================================
    # LINEには必ず200を返す
    # ==================================

    print("Webhook処理完了")

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

    print(
        f"Bot起動: PORT={port}"
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
