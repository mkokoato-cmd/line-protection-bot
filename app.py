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

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")


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
# 荒らし登録データ
#
# group_id
#   └ user_id
#       └ user_name
# ==========================================

spam_users = {}


# ==========================================
# 最後に荒らし登録された人
# group_id -> user_id
# ==========================================

last_spam_user = {}


# ==========================================
# ユーザー名キャッシュ
# ==========================================

user_names = {}


# ==========================================
# メッセージIDからユーザーIDを調べる
# ==========================================

message_users = {}


# ==========================================
# メッセージIDからグループIDを調べる
# ==========================================

message_groups = {}


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
            "LINE返信エラー:",
            e
        )


# ==========================================
# ユーザー名取得
#
# グループ内ならグループメンバーAPIを優先
# ==========================================

def get_user_name(user_id, group_id=None):

    if not user_id:
        return "不明"

    # キャッシュ
    if user_id in user_names:
        return user_names[user_id]

    if not CHANNEL_ACCESS_TOKEN:
        return "不明"

    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

    # --------------------------------------
    # グループメンバーの場合
    # --------------------------------------

    if group_id:

        url = (
            f"{LINE_API}/group/"
            f"{group_id}/member/"
            f"{user_id}"
        )

        try:

            response = requests.get(
                url,
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:

                data = response.json()

                name = data.get(
                    "displayName",
                    "不明"
                )

                user_names[user_id] = name

                return name

        except Exception as e:

            print(
                "グループユーザー名取得エラー:",
                e
            )

    # --------------------------------------
    # 通常プロフィール取得
    # --------------------------------------

    url = f"{LINE_API}/profile/{user_id}"

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:

            data = response.json()

            name = data.get(
                "displayName",
                "不明"
            )

            user_names[user_id] = name

            return name

    except Exception as e:

        print(
            "プロフィール取得エラー:",
            e
        )

    return "不明"


# ==========================================
# Discord通知 共通
# ==========================================

def send_discord_message(content):

    if not DISCORD_WEBHOOK_URL:
        print("Discord Webhook未設定")
        return

    data = {
        "content": content
    }

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=data,
            timeout=10
        )

        print(
            "Discord:",
            response.status_code
        )

    except Exception as e:

        print(
            "Discord通知エラー:",
            e
        )


# ==========================================
# Discord
# 荒らし検知通知
# ==========================================

def send_discord_notification(
    user_name,
    user_id,
    text
):

    content = (
        "🚨 **荒らし検知**\n"
        f"名前: {user_name}\n"
        f"LINEユーザーID: `{user_id}`\n"
        f"メッセージ: {text}"
    )

    send_discord_message(content)


# ==========================================
# Discord
# 禁句検知通知
# ==========================================

def send_discord_forbidden_notification(
    user_name,
    user_id,
    text,
    forbidden_word
):

    content = (
        "🚨 **禁句検知 → 荒らし登録**\n"
        f"名前: {user_name}\n"
        f"LINEユーザーID: `{user_id}`\n"
        f"検出された禁句: `{forbidden_word}`\n"
        f"メッセージ: {text}"
    )

    send_discord_message(content)


# ==========================================
# Discord
# 手動退会対象通知
# ==========================================

def send_discord_kick_notification(
    user_name,
    user_id
):

    content = (
        "⚠️ **手動退会対象ユーザー**\n"
        f"名前: {user_name}\n"
        f"LINEユーザーID: `{user_id}`\n\n"
        "LINEアプリで管理者が確認して、"
        "必要なら手動で退会させてください。"
    )

    send_discord_message(content)


# ==========================================
# Discord
# ID通知
# ==========================================

def send_discord_id_notification(
    user_name,
    user_id
):

    content = (
        "🆔 **LINEユーザーID**\n"
        f"名前: {user_name}\n"
        f"LINEユーザーID: `{user_id}`"
    )

    send_discord_message(content)


# ==========================================
# Discord
# 荒らし名簿
# ==========================================

def send_discord_roster(roster):

    if not roster:

        content = (
            "📋 **荒らし登録一覧**\n"
            "現在、登録者はいません。"
        )

        send_discord_message(content)

        return

    lines = [
        "📋 **荒らし登録一覧**"
    ]

    number = 1

    for user_id, user_name in roster.items():

        lines.append(
            f"{number}. {user_name}\n"
            f"   LINEユーザーID: `{user_id}`"
        )

        number += 1

    send_discord_message(
        "\n".join(lines)
    )


# ==========================================
# Discord
# 荒らし登録通知
# ==========================================

def send_discord_register_notification(
    user_name,
    user_id
):

    content = (
        "🚨 **荒らし登録**\n"
        f"名前: {user_name}\n"
        f"LINEユーザーID: `{user_id}`"
    )

    send_discord_message(content)


# ==========================================
# Discord
# 荒らし削除通知
# ==========================================

def send_discord_delete_notification(
    user_name,
    user_id
):

    content = (
        "🗑️ **荒らし登録削除**\n"
        f"名前: {user_name}\n"
        f"LINEユーザーID: `{user_id}`"
    )

    send_discord_message(content)


# ==========================================
# 荒らし登録
# ==========================================

def register_spam_user(
    group_id,
    user_id,
    user_name
):

    if not group_id or not user_id:
        return

    if group_id not in spam_users:

        spam_users[group_id] = {}

    spam_users[group_id][user_id] = user_name

    last_spam_user[group_id] = user_id

    user_names[user_id] = user_name


# ==========================================
# 荒らし削除
# ==========================================

def delete_spam_user(
    group_id,
    user_id
):

    if not group_id or not user_id:
        return False

    if group_id not in spam_users:
        return False

    if user_id not in spam_users[group_id]:
        return False

    del spam_users[group_id][user_id]

    if (
        group_id in last_spam_user
        and last_spam_user[group_id] == user_id
    ):

        del last_spam_user[group_id]

    return True


# ==========================================
# 荒らし一覧取得
# ==========================================

def get_roster(group_id):

    if not group_id:
        return {}

    return spam_users.get(
        group_id,
        {}
    )


# ==========================================
# メインWebhook
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

    # --------------------------------------
    # 署名確認
    # --------------------------------------

    if not verify_signature(
        body,
        signature
    ):

        print("署名エラー")

        abort(400)

    data = request.get_json()

    events = data.get(
        "events",
        []
    )

    # ======================================
    # イベント処理
    # ======================================

    for event in events:

        # ----------------------------------
        # メッセージイベント以外は無視
        # ----------------------------------

        if event.get("type") != "message":
            continue

        message = event.get(
            "message",
            {}
        )

        # ----------------------------------
        # テキスト以外は無視
        # ----------------------------------

        if message.get("type") != "text":
            continue

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

        group_id = source.get(
            "groupId"
        )

        message_id = message.get(
            "id"
        )

        # ----------------------------------
        # ユーザー名
        # ----------------------------------

        user_name = get_user_name(
            user_id,
            group_id
        )

        # ----------------------------------
        # メッセージIDを保存
        # ----------------------------------

        if message_id and user_id:

            message_users[
                message_id
            ] = user_id

        if message_id and group_id:

            message_groups[
                message_id
            ] = group_id

        # ==================================
        # 返信先ユーザーを取得
        # ==================================

        quoted_message_id = message.get(
            "quotedMessageId"
        )

        quoted_user_id = None
        quoted_user_name = None

        if quoted_message_id:

            quoted_user_id = (
                message_users.get(
                    quoted_message_id
                )
            )

            quoted_group_id = (
                message_groups.get(
                    quoted_message_id
                )
            )

            if quoted_user_id:

                quoted_user_name = get_user_name(
                    quoted_user_id,
                    group_id or quoted_group_id
                )

        # ==================================
        # コマンド
        # ==================================

        # ----------------------------------
        # 禁句一覧
        # ----------------------------------

        if text == "禁句一覧":

            forbidden_text = "\n".join(
                f"・{word}"
                for word in FORBIDDEN_WORDS
            )

            reply_message(
                reply_token,
                "🚫 禁句一覧\n\n"
                + forbidden_text
            )

            continue

        # ----------------------------------
        # 荒らし一覧
        # ----------------------------------

        if text == "!荒らし一覧":

            if not group_id:

                reply_message(
                    reply_token,
                    "このコマンドはグループで使用してください。"
                )

                continue

            roster = get_roster(
                group_id
            )

            if not roster:

                reply_message(
                    reply_token,
                    "📋 荒らし登録者はいません。"
                )

            else:

                names = []

                number = 1

                for registered_user_id, registered_name in roster.items():

                    names.append(
                        f"{number}. {registered_name}"
                    )

                    number += 1

                reply_message(
                    reply_token,
                    "📋 荒らし登録一覧\n\n"
                    + "\n".join(names)
                )

            # DiscordにはID付きで送信
            send_discord_roster(
                roster
            )

            continue

        # ----------------------------------
        # 荒らし削除
        #
        # 返信した相手を優先
        # ----------------------------------

        if text == "!荒らし削除":

            if not group_id:

                reply_message(
                    reply_token,
                    "このコマンドはグループで使用してください。"
                )

                continue

            target_user_id = quoted_user_id

            # 返信していない場合
            # 最後の荒らし登録者を対象
            if not target_user_id:

                target_user_id = last_spam_user.get(
                    group_id
                )

            if not target_user_id:

                reply_message(
                    reply_token,
                    "削除対象の荒らし登録者がいません。\n"
                    "削除したい人のメッセージに返信して\n"
                    "!荒らし削除\n"
                    "と送ってください。"
                )

                continue

            target_name = get_user_name(
                target_user_id,
                group_id
            )

            if delete_spam_user(
                group_id,
                target_user_id
            ):

                reply_message(
                    reply_token,
                    "🗑️ 荒らし登録を削除しました。\n\n"
                    f"対象: {target_name}"
                )

                send_discord_delete_notification(
                    target_name,
                    target_user_id
                )

            else:

                reply_message(
                    reply_token,
                    "そのユーザーは荒らし登録されていません。"
                )

            continue

        # ----------------------------------
        # 荒らし登録
        #
        # 返信した相手を登録
        # ----------------------------------

        if text == "!荒らし":

            if not group_id:

                reply_message(
                    reply_token,
                    "このコマンドはグループで使用してください。"
                )

                continue

            # 返信必須
            if not quoted_user_id:

                reply_message(
                    reply_token,
                    "⚠️ 荒らし登録する相手のメッセージに返信して\n"
                    "!荒らし\n"
                    "と送ってください。"
                )

                continue

            # 自分自身は禁止
            if quoted_user_id == user_id:

                reply_message(
                    reply_token,
                    "自分自身を荒らし登録することはできません。"
                )

                continue

            target_name = quoted_user_name

            if not target_name:

                target_name = get_user_name(
                    quoted_user_id,
                    group_id
                )

            # 登録
            register_spam_user(
                group_id,
                quoted_user_id,
                target_name
            )

            reply_message(
                reply_token,
                "🚨 荒らし登録しました。\n\n"
                f"対象: {target_name}\n\n"
                "必要なら !kick で"
                "手動退会対象として通知できます。"
            )

            send_discord_register_notification(
                target_name,
                quoted_user_id
            )

            continue

        # ----------------------------------
        # 手動退会対象
        #
        # 返信した相手を優先
        # ----------------------------------

        if text == "!kick":

            if not group_id:

                reply_message(
                    reply_token,
                    "このコマンドはグループで使用してください。"
                )

                continue

            target_user_id = quoted_user_id

            # 返信していない場合
            # 最後に荒らし登録された人
            if not target_user_id:

                target_user_id = last_spam_user.get(
                    group_id
                )

            if not target_user_id:

                reply_message(
                    reply_token,
                    "⚠️ 退会対象が見つかりません。\n\n"
                    "退会させたい人のメッセージに返信して\n"
                    "!kick\n"
                    "と送ってください。"
                )

                continue

            target_name = get_user_name(
                target_user_id,
                group_id
            )

            # LINEへ通知
            reply_message(
                reply_token,
                "⚠️ 退会対象ユーザー\n\n"
                f"対象: {target_name}\n\n"
                "LINEアプリで管理者が確認して、"
                "必要なら手動で退会させてください。"
            )

            # Discordへ通知
            send_discord_kick_notification(
                target_name,
                target_user_id
            )

            continue

        # ----------------------------------
        # ID確認
        # ----------------------------------

        if text == "!id":

            send_discord_id_notification(
                user_name,
                user_id
            )

            # LINEにはIDを表示しない
            reply_message(
                reply_token,
                "🆔 LINEユーザーIDを"
                "Discordへ送信しました。"
            )

            continue

        # ==================================
        # 禁句検知
        # ==================================

        detected_word = None

        for forbidden_word in FORBIDDEN_WORDS:

            if forbidden_word in text:

                detected_word = forbidden_word

                break

        if detected_word:

            # --------------------------------
            # グループ内だけ荒らし登録
            # --------------------------------

            if group_id and user_id:

                register_spam_user(
                    group_id,
                    user_id,
                    user_name
                )

                # Discord 禁句通知
                send_discord_forbidden_notification(
                    user_name,
                    user_id,
                    text,
                    detected_word
                )

                # Discord 荒らし検知通知
                send_discord_notification(
                    user_name,
                    user_id,
                    text
                )

                # LINE通知
                reply_message(
                    reply_token,
                    "🚨 禁句を検知しました。\n\n"
                    f"対象: {user_name}\n"
                    "荒らし登録しました。"
                )

            continue

        # ==================================
        # 通常メッセージ
        # ==================================

        print(
            f"通常メッセージ: "
            f"{user_name} / {text}"
        )

    return "OK"


# ==========================================
# ヘルスチェック
# ==========================================

@app.route(
    "/",
    methods=["GET"]
)
def index():

    return "LINE Protection Bot is running!"


# ==========================================
# Render起動
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
