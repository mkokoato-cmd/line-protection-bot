import os
import hmac
import hashlib
import base64

import requests
from flask import Flask, request, abort
from supabase import create_client


# ==========================================
# Flask
# ==========================================

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
# Supabase設定
# ==========================================

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL"
)

SUPABASE_KEY = os.environ.get(
    "SUPABASE_KEY"
)


if not SUPABASE_URL:
    raise RuntimeError(
        "SUPABASE_URLが設定されていません"
    )


if not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_KEYが設定されていません"
    )


supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


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
# メモリキャッシュ
# ==========================================

user_names = {}


# ==========================================
# Supabase
# ユーザー名保存
# ==========================================

def save_user_name(user_id, user_name):

    if not user_id:
        return

    if not user_name:
        user_name = "不明"

    try:

        supabase.table(
            "user_profiles"
        ).upsert(
            {
                "user_id": user_id,
                "user_name": user_name
            },
            on_conflict="user_id"
        ).execute()

    except Exception as e:

        print(
            "Supabaseユーザー名保存エラー:",
            e
        )


# ==========================================
# Supabase
# キャッシュユーザー名取得
# ==========================================

def get_cached_user_name(user_id):

    if not user_id:
        return None

    try:

        result = supabase.table(
            "user_profiles"
        ).select(
            "user_name"
        ).eq(
            "user_id",
            user_id
        ).limit(
            1
        ).execute()

        if result.data:

            user_name = result.data[0].get(
                "user_name"
            )

            if user_name:

                user_names[user_id] = user_name

                return user_name

    except Exception as e:

        print(
            "Supabaseユーザー名取得エラー:",
            e
        )

    return None


# ==========================================
# Supabase
# メッセージ保存
# ==========================================

def save_message(
    message_id,
    user_id,
    group_id
):

    if not message_id:
        return

    if not user_id:
        return

    try:

        supabase.table(
            "message_history"
        ).upsert(
            {
                "message_id": message_id,
                "user_id": user_id,
                "group_id": group_id
            },
            on_conflict="message_id"
        ).execute()

    except Exception as e:

        print(
            "Supabaseメッセージ保存エラー:",
            e
        )


# ==========================================
# Supabase
# メッセージ情報取得
# ==========================================

def get_message_info(message_id):

    if not message_id:
        return None

    try:

        result = supabase.table(
            "message_history"
        ).select(
            "user_id, group_id"
        ).eq(
            "message_id",
            message_id
        ).limit(
            1
        ).execute()

        if result.data:

            return result.data[0]

    except Exception as e:

        print(
            "Supabaseメッセージ取得エラー:",
            e
        )

    return None


# ==========================================
# 荒らし登録
# ==========================================

def register_spam_user(
    group_id,
    user_id,
    user_name
):

    if not group_id:
        return False

    if not user_id:
        return False

    if not user_name:
        user_name = "不明"

    try:

        # 荒らし登録

        supabase.table(
            "spam_users"
        ).upsert(
            {
                "group_id": group_id,
                "user_id": user_id,
                "user_name": user_name
            },
            on_conflict="group_id,user_id"
        ).execute()


        # 最後に登録した荒らし

        supabase.table(
            "last_spam"
        ).upsert(
            {
                "group_id": group_id,
                "user_id": user_id
            },
            on_conflict="group_id"
        ).execute()


        # ユーザー名保存

        save_user_name(
            user_id,
            user_name
        )


        # メモリキャッシュ

        user_names[user_id] = user_name


        print(
            "荒らし登録:",
            group_id,
            user_id,
            user_name
        )

        return True

    except Exception as e:

        print(
            "Supabase荒らし登録エラー:",
            e
        )

        return False


# ==========================================
# 荒らし削除
# ==========================================

def delete_spam_user(
    group_id,
    user_id
):

    if not group_id:
        return False

    if not user_id:
        return False

    try:

        result = supabase.table(
            "spam_users"
        ).select(
            "user_id"
        ).eq(
            "group_id",
            group_id
        ).eq(
            "user_id",
            user_id
        ).limit(
            1
        ).execute()

        if not result.data:

            return False


        # 荒らし削除

        supabase.table(
            "spam_users"
        ).delete().eq(
            "group_id",
            group_id
        ).eq(
            "user_id",
            user_id
        ).execute()


        # 最後の荒らし情報から削除

        supabase.table(
            "last_spam"
        ).delete().eq(
            "group_id",
            group_id
        ).eq(
            "user_id",
            user_id
        ).execute()


        print(
            "荒らし削除:",
            group_id,
            user_id
        )

        return True

    except Exception as e:

        print(
            "Supabase荒らし削除エラー:",
            e
        )

        return False


# ==========================================
# 荒らしか確認
# ==========================================

def is_spam_user(
    group_id,
    user_id
):

    if not group_id:
        return False

    if not user_id:
        return False

    try:

        result = supabase.table(
            "spam_users"
        ).select(
            "user_id"
        ).eq(
            "group_id",
            group_id
        ).eq(
            "user_id",
            user_id
        ).limit(
            1
        ).execute()

        return bool(
            result.data
        )

    except Exception as e:

        print(
            "Supabase荒らし確認エラー:",
            e
        )

        return False


# ==========================================
# 荒らし一覧取得
# ==========================================

def get_roster(group_id):

    if not group_id:
        return {}

    try:

        result = supabase.table(
            "spam_users"
        ).select(
            "user_id, user_name"
        ).eq(
            "group_id",
            group_id
        ).order(
            "created_at"
        ).execute()

        roster = {}

        for row in result.data:

            user_id = row.get(
                "user_id"
            )

            user_name = row.get(
                "user_name"
            ) or "不明"

            if user_id:

                roster[user_id] = user_name

        return roster

    except Exception as e:

        print(
            "Supabase荒らし一覧取得エラー:",
            e
        )

        return {}


# ==========================================
# 最後に登録した荒らし取得
# ==========================================

def get_last_spam_user(group_id):

    if not group_id:
        return None

    try:

        result = supabase.table(
            "last_spam"
        ).select(
            "user_id"
        ).eq(
            "group_id",
            group_id
        ).limit(
            1
        ).execute()

        if result.data:

            return result.data[0].get(
                "user_id"
            )

    except Exception as e:

        print(
            "Supabase最後の荒らし取得エラー:",
            e
        )

    return None


# ==========================================
# LINE署名確認
# ==========================================

def verify_signature(
    body,
    signature
):

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
    ).decode(
        "utf-8"
    )

    return hmac.compare_digest(
        expected_signature,
        signature
    )


# ==========================================
# LINE返信
# ==========================================

def reply_message(
    reply_token,
    text
):

    if not CHANNEL_ACCESS_TOKEN:
        print(
            "CHANNEL_ACCESS_TOKEN未設定"
        )
        return

    if not reply_token:
        return

    url = (
        f"{LINE_API}/message/reply"
    )

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
            "LINE返信エラー:",
            e
        )


# ==========================================
# LINEユーザー名取得
# ==========================================

def get_user_name(
    user_id,
    group_id=None
):

    if not user_id:
        return "不明"


    # メモリキャッシュ

    if user_id in user_names:

        return user_names[user_id]


    # Supabaseキャッシュ

    cached_name = get_cached_user_name(
        user_id
    )

    if cached_name:

        return cached_name


    if not CHANNEL_ACCESS_TOKEN:
        return "不明"


    headers = {
        "Authorization":
        f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }


    # グループメンバー取得

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

                save_user_name(
                    user_id,
                    name
                )

                return name

        except Exception as e:

            print(
                "グループユーザー名取得エラー:",
                e
            )


    # 通常プロフィール取得

    url = (
        f"{LINE_API}/profile/"
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

            save_user_name(
                user_id,
                name
            )

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


    # Discord最大文字数対策

    if len(content) > 1900:

        content = (
            content[:1900]
            + "\n…"
        )

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
# Discord：禁句検知
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

    send_discord_message(
        content
    )
