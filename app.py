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
# 荒らし名簿
# ==========================================

# グループごとの荒らし名簿
#
# {
#     "group_id": {
#         "user_id": "名前"
#     }
# }
#
spam_users = {}


# ==========================================
# グループごとの最後の荒らし
# ==========================================

last_spam_user = {}


# ==========================================
# ユーザー名保存
# ==========================================

user_names = {}


# ==========================================
# メッセージID → ユーザーID
# ==========================================

# LINEの返信先を特定するために使用
#
# {
#     "LINE message ID": "LINE User ID"
# }
#
message_users = {}


# ==========================================
# メッセージID → グループID
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
        "Authorization":
            f"Bearer {CHANNEL_ACCESS_TOKEN}"
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

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={
                "content": discord_message
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
        return

    discord_message = (
        "🚫 禁句検知！\n\n"
        f"👤 名前：{user_name}\n"
        f"🆔 LINE User ID：{user_id}\n"
        f"🚨 禁句：{forbidden_word}\n"
        f"💬 メッセージ：{text}\n\n"
        "⚠️ 荒らしとして自動登録しました。"
    )

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={
                "content": discord_message
            },
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

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={
                "content": discord_message
            },
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
# Discord ID確認通知
# ==========================================

def send_discord_id_notification(
    user_name,
    user_id
):

    if not DISCORD_WEBHOOK_URL:
        return

    discord_message = (
        "🆔 LINE User ID確認\n\n"
        f"👤 名前：{user_name}\n"
        f"🆔 LINE User ID：{user_id}"
    )

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={
                "content": discord_message
            },
            timeout=10
        )

        print(
            "Discord ID:",
            response.status_code,
            response.text
        )

    except Exception as e:

        print(
            "Discord ID notification error:",
            e
        )


# ==========================================
# Discord荒らし名簿
# ==========================================

def send_discord_roster(roster):

    if not DISCORD_WEBHOOK_URL:
        return

    if not roster:

        message = (
            "📋 荒らし名簿\n\n"
            "現在、登録者はいません。"
        )

    else:

        lines = [
            "📋 荒らし名簿",
            "",
            f"登録人数：{len(roster)}人",
            ""
        ]

        for number, (
            user_id,
            user_name
        ) in enumerate(
            roster.items(),
            start=1
        ):

            lines.append(
                f"{number}. {user_name}"
            )

            lines.append(
                f"   🆔 LINE User ID：{user_id}"
            )

        message = "\n".join(lines)

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={
                "content": message
            },
            timeout=10
        )

        print(
            "Discord roster:",
            response.status_code,
            response.text
        )

    except Exception as e:

        print(
            "Discord roster error:",
            e
        )


# ==========================================
# Discord荒らし登録通知
# ==========================================

def send_discord_register_notification(
    user_name,
    user_id
):

    if not DISCORD_WEBHOOK_URL:
        return

    message = (
        "🚨 荒らし登録\n\n"
        f"👤 名前：{user_name}\n"
        f"🆔 LINE User ID：{user_id}\n\n"
        "📋 荒らし名簿に登録しました。"
    )

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={
                "content": message
            },
            timeout=10
        )

        print(
            "Discord register:",
            response.status_code,
            response.text
        )

    except Exception as e:

        print(
            "Discord register error:",
            e
        )


# ==========================================
# Discord荒らし削除通知
# ==========================================

def send_discord_delete_notification(
    user_name,
    user_id
):

    if not DISCORD_WEBHOOK_URL:
        return

    message = (
        "🗑️ 荒らし名簿から削除\n\n"
        f"👤 名前：{user_name}\n"
        f"🆔 LINE User ID：{user_id}"
    )

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={
                "content": message
            },
            timeout=10
        )

        print(
            "Discord delete:",
            response.status_code,
            response.text
        )

    except Exception as e:

        print(
            "Discord delete error:",
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

        print(
            "Profile status:",
            response.status_code,
            response.text
        )

    except Exception as e:

        print(
            "Profile error:",
            e
        )

    return "不明なユーザー"


# ==========================================
# 荒らし登録
# ==========================================

def register_spam_user(
    group_id,
    user_id,
    user_name
):

    if not group_id:
        return

    if group_id not in spam_users:

        spam_users[group_id] = {}

    spam_users[group_id][
        user_id
    ] = user_name

    last_spam_user[
        group_id
    ] = user_id


# ==========================================
# 荒らし削除
# ==========================================

def delete_spam_user(
    group_id,
    user_id
):

    if not group_id:
        return False

    roster = spam_users.get(
        group_id,
        {}
    )

    if user_id not in roster:
        return False

    del roster[user_id]

    if last_spam_user.get(
        group_id
    ) == user_id:

        last_spam_user.pop(
            group_id,
            None
        )

    return True


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

        data = request.json

        events = data.get(
            "events",
            []
        )

    except Exception:

        return "OK"


    # ======================================
    # イベント処理
    # ======================================

    for event in events:

        if event.get("type") != "message":
            continue


        message = event.get(
            "message",
            {}
        )


        if message.get("type") != "text":
            continue


        # ==================================
        # 情報取得
        # ==================================

        text = message.get(
            "text",
            ""
        ).strip()

        message_id = message.get(
            "id"
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


        if not user_id:
            continue


        # ==================================
        # ユーザー名
        # ==================================

        user_name = get_user_name(
            user_id
        )

        user_names[
            user_id
        ] = user_name


        # ==================================
        # メッセージIDを保存
        # ==================================

        if message_id:

            message_users[
                message_id
            ] = user_id

            if group_id:

                message_groups[
                    message_id
                ] = group_id


        # ==================================
        # 返信先メッセージID
        # ==================================

        quoted_message_id = message.get(
            "quotedMessageId"
        )


        # ==================================
        # 返信先ユーザーID取得
        # ==================================

        quoted_user_id = None

        if quoted_message_id:

            quoted_user_id = message_users.get(
                quoted_message_id
            )


        # ==================================
        # 返信先ユーザー名取得
        # ==================================

        quoted_user_name = None

        if quoted_user_id:

            quoted_user_name = user_names.get(
                quoted_user_id
            )

            if not quoted_user_name:

                quoted_user_name = get_user_name(
                    quoted_user_id
                )

                user_names[
                    quoted_user_id
                ] = quoted_user_name


        # ==================================
        # 禁句一覧
        # ==================================

        if text == "禁句一覧":

            if reply_token:

                if FORBIDDEN_WORDS:

                    word_list = "\n".join(
                        f"{i}. {word}"
                        for i, word in enumerate(
                            FORBIDDEN_WORDS,
                            start=1
                        )
                    )

                    reply_message(
                        reply_token,
                        "🚫 禁句一覧\n\n"
                        f"{word_list}\n\n"
                        f"合計：{len(FORBIDDEN_WORDS)}個"
                    )

                else:

                    reply_message(
                        reply_token,
                        "🚫 禁句一覧\n\n"
                        "現在、禁句は登録されていません。"
                    )

            continue


        # ==================================
        # !荒らし一覧
        # ==================================

        if text == "!荒らし一覧":

            if not group_id:

                if reply_token:

                    reply_message(
                        reply_token,
                        "⚠️ このコマンドは"
                        "グループ内で使用してください。"
                    )

                continue


            roster = spam_users.get(
                group_id,
                {}
            )


            # ==================================
            # LINEには名前だけ
            # ==================================

            if not roster:

                line_message = (
                    "📋 荒らし名簿\n\n"
                    "現在、登録者はいません。"
                )

            else:

                lines = [
                    "📋 荒らし名簿",
                    "",
                    f"登録人数：{len(roster)}人",
                    ""
                ]

                for number, user_name in enumerate(
                    roster.values(),
                    start=1
                ):

                    lines.append(
                        f"{number}. {user_name}"
                    )

                line_message = "\n".join(
                    lines
                )


            if reply_token:

                reply_message(
                    reply_token,
                    line_message
                )


            # DiscordにはID付き
            send_discord_roster(
                roster
            )

            continue


        # ==================================
        # !荒らし削除
        # ==================================

        if text == "!荒らし削除":

            if not group_id:

                if reply_token:

                    reply_message(
                        reply_token,
                        "⚠️ このコマンドは"
                        "グループ内で使用してください。"
                    )

                continue


            # ==================================
            # 返信先を削除対象にする
            # ==================================

            target_user_id = quoted_user_id


            # ==================================
            # 返信していない場合は
            # 最後の荒らしを対象にする
            # ==================================

            if not target_user_id:

                target_user_id = last_spam_user.get(
                    group_id
                )


            if not target_user_id:

                if reply_token:

                    reply_message(
                        reply_token,
                        "⚠️ 削除対象がありません。\n\n"
                        "荒らしにした人のメッセージに返信して\n"
                        "!荒らし削除\n"
                        "と入力してください。"
                    )

                continue


            roster = spam_users.get(
                group_id,
                {}
            )


            target_name = roster.get(
                target_user_id,
                user_names.get(
                    target_user_id,
                    "不明なユーザー"
                )
            )


            # ==================================
            # 名簿から削除
            # ==================================

            deleted = delete_spam_user(
                group_id,
                target_user_id
            )


            if not deleted:

                if reply_token:

                    reply_message(
                        reply_token,
                        "⚠️ そのユーザーは"
                        "荒らし名簿に登録されていません。"
                    )

                continue


            # ==================================
            # LINE通知
            # ==================================

            if reply_token:

                reply_message(
                    reply_token,
                    "🗑️ 荒らし名簿から削除しました。\n\n"
                    f"👤 {target_name}"
                )


            # ==================================
            # Discord通知
            # ==================================

            send_discord_delete_notification(
                target_name,
                target_user_id
            )

            continue


        # ==================================
        # !荒らし
        # ==================================

        if text == "!荒らし":

            if not group_id:

                if reply_token:

                    reply_message(
                        reply_token,
                        "⚠️ このコマンドは"
                        "グループ内で使用してください。"
                    )

                continue


            # ==================================
            # 返信先がない場合
            # ==================================

            if not quoted_user_id:

                if reply_token:

                    reply_message(
                        reply_token,
                        "⚠️ 荒らし登録する人の"
                        "メッセージに返信して\n\n"
                        "!荒らし\n\n"
                        "と入力してください。"
                    )

                continue


            # ==================================
            # 自分自身を登録しない
            # ==================================

            if quoted_user_id == user_id:

                if reply_token:

                    reply_message(
                        reply_token,
                        "⚠️ 自分自身は"
                        "荒らし登録できません。"
                    )

                continue


            # ==================================
            # 荒らし名簿へ登録
            # ==================================

            register_spam_user(
                group_id,
                quoted_user_id,
                quoted_user_name or "不明なユーザー"
            )


            # ==================================
            # LINE通知
            # ==================================

            line_message = (
                "🚨 荒らし登録！\n\n"
                f"👤 {quoted_user_name or '不明なユーザー'}\n\n"
                "📋 荒らし名簿に登録しました。\n\n"
                "名簿を見る場合は\n"
                "!荒らし一覧\n\n"
                "退会対象を確認する場合は\n"
                "!kick"
            )


            if reply_token:

                reply_message(
                    reply_token,
                    line_message
                )


            # ==================================
            # Discord通知
            # ==================================

            send_discord_register_notification(
                quoted_user_name or "不明なユーザー",
                quoted_user_id
            )

            continue


        # ==================================
        # !kick
        # ==================================

        if text == "!kick":

            if not group_id:

                if reply_token:

                    reply_message(
                        reply_token,
                        "⚠️ このコマンドは"
                        "グループ内で使用してください。"
                    )

                continue


            # ==================================
            # 最後に登録された荒らし
            # ==================================

            target_user_id = last_spam_user.get(
                group_id
            )


            if not target_user_id:

                if reply_token:

                    reply_message(
                        reply_token,
                        "⚠️ 荒らし対象がありません。\n\n"
                        "荒らしにしたい人のメッセージに返信して\n"
                        "!荒らし\n"
                        "と入力してください。"
                    )

                continue


            target_name = user_names.get(
                target_user_id,
                "不明なユーザー"
            )


            # ==================================
            # LINEにはIDを表示しない
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
            # DiscordにはID表示
            # ==================================

            send_discord_kick_notification(
                target_name,
                target_user_id
            )

            continue


        # ==================================
        # !id
        # ==================================

        if text == "!id":

            if reply_token:

                reply_message(
                    reply_token,
                    "🆔 LINE User IDを\n"
                    "Discordへ送信しました。"
                )


            send_discord_id_notification(
                user_name,
                user_id
            )

            continue


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
        # 禁句発見
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
            # 禁句を使った本人を
            # 自動で荒らし登録
            # ==================================

            register_spam_user(
                group_id,
                user_id,
                user_name
            )


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
