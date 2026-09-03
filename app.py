import os
import sqlite3
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
# 管理者設定
# ==========================================

ADMIN_USER_IDS = {
    "Ud1066a8c57c09ff166fac3b7aa158785",
}


def is_admin(user_id):
    if not user_id:
        return False

    return user_id in ADMIN_USER_IDS


# ==========================================
# 禁句
# ==========================================

FORBIDDEN_WORDS = [
    "殺す",
    "死ね",
    "死んで",
    "キモイ",
]


# ==========================================
# SQLite保存場所
# ==========================================

DB_PATH = os.environ.get(
    "DB_PATH",
    "/var/data/line_protection.db"
)


# ==========================================
# 一時保存
# ==========================================

user_names = {}

message_users = {}

message_groups = {}


# ==========================================
# データベース初期化
# ==========================================

def init_db():

    folder = os.path.dirname(DB_PATH)

    if folder:
        os.makedirs(folder, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS spam_users (
            group_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            user_name TEXT,
            PRIMARY KEY (group_id, user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS last_spam (
            group_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL
        )
    """)

    conn.commit()

    conn.close()

    print("SQLite初期化完了:", DB_PATH)


# ==========================================
# 荒らし登録
# ==========================================

def register_spam_user(group_id, user_id, user_name):

    if not group_id:
        return

    if not user_id:
        return

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO spam_users
        (group_id, user_id, user_name)
        VALUES (?, ?, ?)
    """, (
        group_id,
        user_id,
        user_name
    ))

    cursor.execute("""
        INSERT OR REPLACE INTO last_spam
        (group_id, user_id)
        VALUES (?, ?)
    """, (
        group_id,
        user_id
    ))

    conn.commit()

    conn.close()

    user_names[user_id] = user_name

    print(
        "荒らし登録:",
        group_id,
        user_id,
        user_name
    )


# ==========================================
# 荒らし削除
# ==========================================

def delete_spam_user(group_id, user_id):

    if not group_id:
        return False

    if not user_id:
        return False

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_name
        FROM spam_users
        WHERE group_id = ?
        AND user_id = ?
    """, (
        group_id,
        user_id
    ))

    result = cursor.fetchone()

    if not result:

        conn.close()

        return False

    cursor.execute("""
        DELETE FROM spam_users
        WHERE group_id = ?
        AND user_id = ?
    """, (
        group_id,
        user_id
    ))

    cursor.execute("""
        DELETE FROM last_spam
        WHERE group_id = ?
        AND user_id = ?
    """, (
        group_id,
        user_id
    ))

    conn.commit()

    conn.close()

    return True


# ==========================================
# 荒らしか確認
# ==========================================

def is_spam_user(group_id, user_id):

    if not group_id:
        return False

    if not user_id:
        return False

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute("""
        SELECT 1
        FROM spam_users
        WHERE group_id = ?
        AND user_id = ?
        LIMIT 1
    """, (
        group_id,
        user_id
    ))

    result = cursor.fetchone()

    conn.close()

    return result is not None


# ==========================================
# 荒らし一覧取得
# ==========================================

def get_roster(group_id):

    if not group_id:
        return {}

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id, user_name
        FROM spam_users
        WHERE group_id = ?
        ORDER BY rowid ASC
    """, (
        group_id,
    ))

    rows = cursor.fetchall()

    conn.close()

    roster = {}

    for user_id, user_name in rows:

        roster[user_id] = user_name or "不明"

    return roster


# ==========================================
# 最後に登録した荒らし
# ==========================================

def get_last_spam_user(group_id):

    if not group_id:
        return None

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id
        FROM last_spam
        WHERE group_id = ?
    """, (
        group_id,
    ))

    result = cursor.fetchone()

    conn.close()

    if result:
        return result[0]

    return None


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

    if not reply_token:
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
# LINEユーザー名取得
# ==========================================

def get_user_name(user_id, group_id=None):

    if not user_id:
        return "不明"

    if user_id in user_names:
        return user_names[user_id]

    if not CHANNEL_ACCESS_TOKEN:
        return "不明"

    headers = {
        "Authorization":
        f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }


    # --------------------------------------
    # グループメンバーとして取得
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
    # プロフィール取得
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
# Discord送信
# ==========================================

def send_discord_message(content):

    if not DISCORD_WEBHOOK_URL:

        print(
            "Discord Webhook未設定"
        )

        return

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={
                "content": content
            },
            timeout=10
        )

        print(
            "Discord:",
            response.status_code,
            response.text
        )

    except Exception as e:

        print(
            "Discord通知エラー:",
            e
        )


# ==========================================
# Discord：荒らし検知
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
        f"メッセージ: {text}\n\n"
        "⚠️ このユーザーは荒らし登録済みです。"
    )

    send_discord_message(content)


# ==========================================
# Discord：禁句
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
        f"メッセージ: {text}\n\n"
        "⚠️ 自動的に荒らし登録しました。"
    )

    send_discord_message(content)


# ==========================================
# Discord：荒らし登録
# ==========================================

def send_discord_register_notification(
    user_name,
    user_id
):

    send_discord_message(
        "🚨 **荒らし登録**\n"
        f"名前: {user_name}\n"
        f"LINEユーザーID: `{user_id}`\n\n"
        "⚠️ このユーザーを荒らしとして登録しました。"
    )


# ==========================================
# Discord：荒らし削除
# ==========================================

def send_discord_delete_notification(
    user_name,
    user_id
):

    send_discord_message(
        "🗑️ **荒らし登録削除**\n"
        f"名前: {user_name}\n"
        f"LINEユーザーID: `{user_id}`"
    )


# ==========================================
# Discord：荒らし一覧
# ==========================================

def send_discord_roster(roster):

    if not roster:

        send_discord_message(
            "📋 **荒らし登録一覧**\n"
            "現在、登録者はいません。"
        )

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
# Discord：kick
# ==========================================

def send_discord_kick_notification(
    user_name,
    user_id
):

    send_discord_message(
        "⚠️ **荒らし・退会対象ユーザー**\n"
        f"名前: {user_name}\n"
        f"LINEユーザーID: `{user_id}`\n\n"
        "このユーザーは退会対象です。\n"
        "LINEアプリで管理者が確認して、"
        "必要なら手動で退会させてください。"
    )


# ==========================================
# Discord：ID
# ==========================================

def send_discord_id_notification(
    user_name,
    user_id
):

    send_discord_message(
        "🆔 **LINEユーザーID**\n"
        f"名前: {user_name}\n"
        f"LINEユーザーID: `{user_id}`"
    )


# ==========================================
# Discord：荒らし発言
# ==========================================

def send_discord_spam_activity(
    user_name,
    user_id,
    text
):

    # Discordの長文対策
    if len(text) > 1500:

        text = text[:1500] + "…"


    send_discord_message(
        "🚨 **荒らし登録者が発言しました**\n"
        f"名前: {user_name}\n"
        f"LINEユーザーID: `{user_id}`\n"
        f"メッセージ: {text}\n\n"
        "⚠️ LINEアプリで確認してください。\n"
        "必要なら管理者が手動で退会させてください。"
    )


# ==========================================
# Discord：退出
# ==========================================

def send_discord_member_left_notification(
    group_id,
    user_id,
    user_name,
    was_spam
):

    if was_spam:

        content = (
            "🚨 **荒らし登録ユーザーの退出を検知**\n\n"
            f"名前: {user_name}\n"
            f"LINEユーザーID: `{user_id}`\n"
            f"グループID: `{group_id}`\n\n"
            "⚠️ このユーザーは荒らし登録されていました。\n"
            "グループからの退出を検知しました。"
        )

    else:

        content = (
            "👋 **グループメンバー退出検知**\n\n"
            f"名前: {user_name}\n"
            f"LINEユーザーID: `{user_id}`\n"
            f"グループID: `{group_id}`\n\n"
            "メンバーの退出を検知しました。"
        )


    send_discord_message(content)


# ==========================================
# DB初期化
# ==========================================

init_db()


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

    if not data:

        return "OK"


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


        # ==================================
        # メンバー退出
        # ==================================

        if event_type == "memberLeft":

            source = event.get(
                "source",
                {}
            )

            group_id = source.get(
                "groupId"
            )


            if not group_id:

                print(
                    "メンバー退出: "
                    "グループID取得失敗"
                )

                continue


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


                user_name = get_user_name(
                    user_id,
                    group_id
                )


                was_spam = is_spam_user(
                    group_id,
                    user_id
                )


                print(
                    "メンバー退出検知:",
                    user_name,
                    user_id
                )


                send_discord_member_left_notification(
                    group_id,
                    user_id,
                    user_name,
                    was_spam
                )


            continue


        # ==================================
        # メンバー参加
        # ==================================

        if event_type == "memberJoined":

            source = event.get(
                "source",
                {}
            )

            group_id = source.get(
                "groupId"
            )


            if not group_id:
                continue


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


                user_name = get_user_name(
                    user_id,
                    group_id
                )


                send_discord_message(
                    "👋 **グループメンバー参加検知**\n\n"
                    f"名前: {user_name}\n"
                    f"LINEユーザーID: `{user_id}`\n"
                    f"グループID: `{group_id}`"
                )


            continue


        # ==================================
        # メッセージ以外
        # ==================================

        if event_type != "message":
            continue


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


        message_id = message.get(
            "id"
        )


        user_name = get_user_name(
            user_id,
            group_id
        )


        # ==================================
        # メッセージ記録
        # ==================================

        if message_id and user_id:

            message_users[
                message_id
            ] = user_id


        if message_id and group_id:

            message_groups[
                message_id
            ] = group_id


        # ==================================
        # 返信先取得
        # ==================================

        quoted_message_id = message.get(
            "quotedMessageId"
        )


        quoted_user_id = None

        quoted_user_name = None


        if quoted_message_id:

            quoted_user_id = message_users.get(
                quoted_message_id
            )


            quoted_group_id = message_groups.get(
                quoted_message_id
            )


            if quoted_user_id:

                quoted_user_name = get_user_name(
                    quoted_user_id,
                    group_id or quoted_group_id
                )


        # ==================================
        # !id
        # ==================================

        if text == "!id":

            if user_id:

                reply_message(
                    reply_token,
                    "🆔 あなたのLINEユーザーID\n\n"
                    + user_id
                )


                send_discord_id_notification(
                    user_name,
                    user_id
                )

            else:

                reply_message(
                    reply_token,
                    "LINEユーザーIDを取得できませんでした。"
                )


            continue


        # ==================================
        # 禁句一覧
        # ==================================

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


        # ==================================
        # 管理者コマンド確認
        # ==================================

        admin_commands = [
            "!荒らし一覧",
            "!荒らし削除",
            "!荒らし",
            "!kick"
        ]


        if text in admin_commands:

            if not is_admin(user_id):

                reply_message(
                    reply_token,
                    "⛔ このコマンドは管理者専用です。"
                )

                continue


        # ==================================
        # !荒らし一覧
        # ==================================

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


            # DiscordにはIDも送る
            send_discord_roster(
                roster
            )


            continue


        # ==================================
        # !荒らし削除
        # ==================================

        if text == "!荒らし削除":

            if not group_id:

                reply_message(
                    reply_token,
                    "このコマンドはグループで使用してください。"
                )

                continue


            target_user_id = quoted_user_id


            # 返信先がなければ最後の登録者
            if not target_user_id:

                target_user_id = get_last_spam_user(
                    group_id
                )


            if not target_user_id:

                reply_message(
                    reply_token,
                    "削除対象が見つかりません。\n\n"
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


        # ==================================
        # !荒らし
        # ==================================

        if text == "!荒らし":

            if not group_id:

                reply_message(
                    reply_token,
                    "このコマンドはグループで使用してください。"
                )

                continue


            if not quoted_user_id:

                reply_message(
                    reply_token,
                    "⚠️ 荒らし登録する相手のメッセージに返信して\n"
                    "!荒らし\n"
                    "と送ってください。"
                )

                continue


            if quoted_user_id == user_id:

                reply_message(
                    reply_token,
                    "自分自身を荒らし登録することはできません。"
                )

                continue


            target_name = (
                quoted_user_name
                or get_user_name(
                    quoted_user_id,
                    group_id
                )
            )


            already_registered = is_spam_user(
                group_id,
                quoted_user_id
            )


            register_spam_user(
                group_id,
                quoted_user_id,
                target_name
            )


            reply_message(
                reply_token,
                "🚨 荒らし登録しました。\n\n"
                f"対象: {target_name}\n\n"
                "このユーザーが今後発言すると、"
                "Discordへ自動通知します。\n\n"
                "!荒らし削除 で登録解除できます。\n"
                "!kick で退会対象としてDiscordへ通知できます。"
            )


            if not already_registered:

                send_discord_register_notification(
                    target_name,
                    quoted_user_id
                )


            continue


        # ==================================
        # !kick
        # ==================================

        if text == "!kick":

            if not group_id:

                reply_message(
                    reply_token,
                    "このコマンドはグループで使用してください。"
                )

                continue


            target_user_id = quoted_user_id


            if not target_user_id:

                target_user_id = get_last_spam_user(
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


            registered = is_spam_user(
                group_id,
                target_user_id
            )


            if not registered:

                reply_message(
                    reply_token,
                    "⚠️ このユーザーは荒らし登録されていません。\n\n"
                    "先に !荒らし で登録してください。"
                )

                continue


            reply_message(
                reply_token,
                "⚠️ 退会対象ユーザー\n\n"
                f"対象: {target_name}\n\n"
                "荒らし登録済みです。\n"
                "LINEアプリで管理者が確認して、"
                "必要なら手動で退会させてください。"
            )


            send_discord_kick_notification(
                target_name,
                target_user_id
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

            if group_id and user_id:

                already_registered = is_spam_user(
                    group_id,
                    user_id
                )


                # 自動荒らし登録
                register_spam_user(
                    group_id,
                    user_id,
                    user_name
                )


                send_discord_forbidden_notification(
                    user_name,
                    user_id,
                    text,
                    detected_word
                )


                if not already_registered:

                    send_discord_register_notification(
                        user_name,
                        user_id
                    )


                reply_message(
                    reply_token,
                    "🚨 禁句を検知しました。\n\n"
                    f"対象: {user_name}\n"
                    f"検出: {detected_word}\n\n"
                    "このユーザーを荒らし登録しました。\n"
                    "今後の発言はDiscordへ通知されます。"
                )


            continue


        # ==================================
        # 荒らし登録者の発言
        # ==================================

        if (
            group_id
            and user_id
            and is_spam_user(
                group_id,
                user_id
            )
        ):

            send_discord_spam_activity(
                user_name,
                user_id,
                text
            )


            reply_message(
                reply_token,
                "🚨 荒らし登録ユーザーを検知しました。\n\n"
                f"対象: {user_name}\n"
                "管理者に通知しました。"
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
# トップページ
# ==========================================

@app.route(
    "/",
    methods=["GET"]
)
def index():

    return "LINE Protection Bot is running!"


# ==========================================
# 起動
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
