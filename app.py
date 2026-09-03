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

        # 登録確認

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


        # last_spamからも削除

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


            roster[user_id] = user_name


        return roster


    except Exception as e:

        print(
            "Supabase荒らし一覧取得エラー:",
            e
        )

        return {}






> Rblack
> Rblack list
# Croom >> room作製(Croom)

# Rblack >> 既読ブリスを消したりします

# Rblack list >> 既読ブリスを確認します

# add simple kicker >> 簡易キッカーを登録します

# alltag >> オールメンション

# amid >> 自分のmidを送信します

# announce >> 取得したアナウンスを送信します

# audio >> テキストを音声にします
audio >> テキストを音声にします(audio:text)

auto join >> 自動参加をオン/オフにします

auto leave >> 強制自動退出をオン/オフします

best friend >> 最も古くからいる友達を出します

black kick >> ブラリスを蹴ります

black list >> ブラリスを確認します

broadcast >> 全グループに送信します(broadcast:text, broadcast:text:gid, gid)

cb >> ブロックされてるか確認

check >> リプライしたメッセージの既読した人を出します

check prefix >> 接頭辞の確認

commands >> 変更したコマンドを送信します

conc >> コマンドを並行実行します(conc:command)

contact >> midから連絡先を送信します(contact:mid)

contact cb >> 送信したアカウントにブロックされているか確認できます

contact info >> 送信されたアカウントの情報を出します

conti >> コマンドを連続実行します(conti:command)

conti run >> 指定した回数指定したコマンドを実行します

copy >> リプライしたメッセージをコピーします

del memo >> メモを消します

del simple kicker >> 簡易キッカーを削除します

delete >> 登録したコマンドを削除します(delete:after command name)

delkicker >> 登録したキッカーを削除します

dis greeting >> あいさつを無効にします

event >> 現在のイベントを操作できます(event:ls, del)

exit >> botを終了します

fhelp >> 説明書を出します

find mid >> 参加中すべてのグループからmidを探します

flex_f >> flex

gid >> gidを送信します

gid all >> 参加しているグループのIDを全て出します

google >> Googleの検索結果のURLを送信します

greeting >> 挨拶を設定します

group >> 所得したGroupを送信します(group, group:gid)

gurl >> グループのURLを出します(gurl, gurl:gid)

help >> 説明書を送信します

invite override >> コテハンで招待します(invite override:name)

invitee >> 招待中のメンバーを送信します

join greeting >> 自動参加時の挨拶をオン/オフします

julia >> 計算します

kick >> ブラリスから消したりします(black:add or del: @mentions)

kickall strong >> 規制が来る可能性大

kicker >> キッカーをログインさせます

kicker prefix >> キッカーの接頭辞を変更します

kicker tokens >> 登録してるキッカーのトークンなどを出します

lyric >> 歌詞を検索して送信します

macro >> 参加マクロ(すぐ凍結します)(macro:num, macro:num:gid)

mailadd >> 廃止しました

mcon >> 取得したContactを送信します(mcon:@mention)

me >> 自身のアカウントを送信します

mea >> いろんな速度を測定します(mea:rcv, noop, send, contact, profile)

memo >> メモを設定します

memo list >> メモの名前一覧を出します

mention macro >> メンションマクロします(mention macro:num: @mention)

mid >> midを送信します

mk >> メンションした人を蹴ります(mk: @mention)

mmid >> midを所得します

msg macro >> メッセージマクロします(msg macro:num:text)

multi close >> 進行中のマルチを閉じます

multi join >> マルチに参加します

multi kickall >> マルチで全蹴りします

multi login >> マルチメンバーをログインさせます

multi open >> マルチを開きます

multi test >> マルチで動作確認します

multi url join >> マルチに参加している人を参加させます

multi users >> マルチに参加してる人を出します

nc >> 指定した値が名前に含まれている人をキャンセルします(nc:name)

nk >> 入力した値を名前に含んだ人を蹴ります(nk:name)

noc >> 指定した値がコテハンに含まれている人をキャンセルします(noc:name)

nock >> 指定した値がコテハンに含まれている人を蹴り、キャンセルします(nock:name)

nok >> 指定した文字がコテハンに含まれている人を蹴ります(nok:name)

notice >> お知らせを送信します

notice on >> 通知をオンにします

op time >> 稼働時間を送信します

override >> コテハンします(override:name: @mention)

paste >> コピーしたメッセージを送信します

ping >> 回線速度的なのを出します

prefix >> 接頭辞を変更します

protect >> 仮保護botを起動します

random exec >> コマンドをランダムで実行します

reboot >> 再起動します(メンテ)

reply run >> リプライしたコマンドを再実行できます

res mention >> メンションに返信します

restore >> 送信取り消し感知を設定します

send >> makuro

send count >> ログインしてから送信したメッセージ数を送信します

send greeting >> 自動参加時のメッセージ

send memo >> メモを送信します

send restore >> 直近の取り消されたメッセージを出します

set auto join message >> 自動参加した時に自動で送信するメッセージを設定します

setting >> 設定状況を送信します

simple kicker >> 簡易キッカーをログインさせます

speed >> 速度を計測します

test >> 動作確認をします

ticket update >> グループのを更新します

time cancel >> 時間間隔を指定してキャンセルします

timeline info >> 共有したタイムラインの情報を出します

tokenadd >> キッカーを追加します(LITEのトークンのみ)(tokenadd:auth token)

train >> 乗り換え案内(ベータ)

unsend >> リプライしたメッセージを取り消します

107: unsend s >> 指定した数、送信取り消します

update >> コマンドを変更します(update:command name:aftar command name)

url >> グループのURLを開閉できます(url:open/close)

use rate >> コマンドの使用率ランキング

weather >> 天気を出します

112: white >> ホワリスから消したりします(white:add or del: @mentions)

white list >> ホワリスを確認します

youtube >> 保存した動画を送信します

トーク荒らし >> トークを荒らします

ハメハメ波 >> エライザのハメ撮り

メンション確認 >> 最後にメンションされたメッセージにリプライします

ログ消し >> メンションした相手を蹴ってログを消します(clear log:@mention)

ロケット団がゲットだぜ！ >> 指定のgidを入れて全蹴りします

参戦 >> なんか

規制確認 >> 規制を確認します
# ==========================================
# 最後に登録した荒らし
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


    # --------------------------------------
    # メモリキャッシュ
    # --------------------------------------

    if user_id in user_names:

        return user_names[user_id]


    # --------------------------------------
    # Supabaseキャッシュ
    # --------------------------------------

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


    # --------------------------------------
    # グループメンバー取得
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


    # --------------------------------------
    # プロフィール取得
    # --------------------------------------

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


    send_discord_message(
        content
    )


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
# Discord：メンバー退出
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
            "⚠️ このユーザーは荒らし登録されていました。"
        )

    else:

        content = (
            "👋 **グループメンバー退出検知**\n\n"
            f"名前: {user_name}\n"
            f"LINEユーザーID: `{user_id}`\n"
            f"グループID: `{group_id}`"
        )


    send_discord_message(
        content
    )


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
    # LINE署名確認
    # --------------------------------------

    if not verify_signature(
        body,
        signature
    ):

        print(
            "署名エラー"
        )

        abort(400)


    data = request.get_json(
        silent=True
    )


    if not data:

        return "OK", 200


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
        # メッセージ以外は無視
        # ==================================

        if event_type != "message":
            continue


        message = event.get(
            "message",
            {}
        )


        # ==================================
        # テキスト以外は無視
        # ==================================

        if message.get("type") != "text":
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
        # メッセージ履歴保存
        # ==================================

        if message_id and user_id:

            save_message(
                message_id,
                user_id,
                group_id
            )


        # ==================================
        # 返信先取得
        # ==================================

        quoted_message_id = message.get(
            "quotedMessageId"
        )


        quoted_user_id = None
        quoted_user_name = None


        if quoted_message_id:

            quoted_info = get_message_info(
                quoted_message_id
            )


            if quoted_info:

                quoted_user_id = quoted_info.get(
                    "user_id"
                )


                quoted_group_id = quoted_info.get(
                    "group_id"
                )


                if quoted_user_id:

                    quoted_user_name = get_user_name(
                        quoted_user_id,
                        group_id
                        or quoted_group_id
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
        # 管理者コマンド
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


                for (
                    registered_user_id,
                    registered_name
                ) in roster.items():

                    names.append(
                        f"{number}. {registered_name}"
                    )

                    number += 1


                reply_message(
                    reply_token,
                    "📋 荒らし登録一覧\n\n"
                    + "\n".join(names)
                )


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


            success = register_spam_user(
                group_id,
                quoted_user_id,
                target_name
            )


            if not success:

                reply_message(
                    reply_token,
                    "❌ 荒らし登録に失敗しました。"
                )

                continue


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


                success = register_spam_user(
                    group_id,
                    user_id,
                    user_name
                )


                if success:

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


                else:

                    reply_message(
                        reply_token,
                        "⚠️ 禁句を検知しましたが、"
                        "荒らし登録に失敗しました。"
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


    return "OK", 200


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
# ヘルスチェック
# ==========================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return {
        "status": "ok",
        "service": "LINE Protection Bot"
    }, 200


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
