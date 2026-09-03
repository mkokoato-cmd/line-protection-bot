import os
import hmac
import hashlib
import base64
import logging

import requests
from flask import Flask, request, abort, jsonify
from dotenv import load_dotenv
from supabase import create_client
from openai import OpenAI


# ==========================================
# 環境変数読み込み
# ==========================================

load_dotenv()


# ==========================================
# Flask
# ==========================================

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# ==========================================
# LINE設定
# ==========================================

CHANNEL_SECRET = os.environ.get("CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN")


# ==========================================
# Supabase設定
# ==========================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


# ==========================================
# OpenAI設定
# ==========================================

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# 使用するモデル
OPENAI_MODEL = os.environ.get(
    "OPENAI_MODEL",
    "gpt-5-mini"
)


# ==========================================
# 必須環境変数チェック
# ==========================================

required_vars = {
    "CHANNEL_SECRET": CHANNEL_SECRET,
    "CHANNEL_ACCESS_TOKEN": CHANNEL_ACCESS_TOKEN,
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_KEY": SUPABASE_KEY,
    "OPENAI_API_KEY": OPENAI_API_KEY,
}

missing_vars = []

for name, value in required_vars.items():
    if not value:
        missing_vars.append(name)

if missing_vars:
    raise RuntimeError(
        "環境変数が設定されていません: "
        + ", ".join(missing_vars)
    )


# ==========================================
# Supabase接続
# ==========================================

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# ==========================================
# OpenAI接続
# ==========================================

openai_client = OpenAI(
    api_key=OPENAI_API_KEY
)


# ==========================================
# AIキャラクター設定
# ==========================================

SYSTEM_PROMPT = """
あなたはLINE上で会話する親しみやすいAIアシスタントです。

ルール:

・日本語で自然に会話する
・親しみやすく話す
・長すぎる文章を避ける
・LINEのチャットらしい返答にする
・必要なら絵文字を少し使う
・分からないことは正直に分からないと言う
・危険な行為を助長しない
・ユーザーの質問にできるだけ役立つ回答をする

返答は基本的に短めで自然な会話にしてください。
"""


# ==========================================
# LINE API
# ==========================================

LINE_REPLY_API = (
    "https://api.line.me/v2/bot/message/reply"
)


# ==========================================
# 署名検証
# ==========================================

def validate_signature(body, signature):

    if not signature:
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
                "text": text[:5000]
            }
        ]
    }

    response = requests.post(
        LINE_REPLY_API,
        headers=headers,
        json=data,
        timeout=15
    )

    if response.status_code >= 400:

        logging.error(
            "LINE返信エラー: %s",
            response.text
        )

    return response


# ==========================================
# Supabase
# 会話履歴取得
# ==========================================

def get_conversation_history(user_id, limit=10):

    try:

        result = (
            supabase
            .table("chat_history")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        rows = result.data or []

        # 古い順に並べ直す
        rows.reverse()

        return rows

    except Exception as error:

        logging.error(
            "履歴取得エラー: %s",
            error
        )

        return []


# ==========================================
# Supabase
# メッセージ保存
# ==========================================

def save_message(
    user_id,
    role,
    content
):

    try:

        data = {
            "user_id": user_id,
            "role": role,
            "content": content
        }

        (
            supabase
            .table("chat_history")
            .insert(data)
            .execute()
        )

    except Exception as error:

        logging.error(
            "メッセージ保存エラー: %s",
            error
        )


# ==========================================
# 会話履歴削除
# ==========================================

def delete_history(user_id):

    try:

        (
            supabase
            .table("chat_history")
            .delete()
            .eq("user_id", user_id)
            .execute()
        )

        return True

    except Exception as error:

        logging.error(
            "履歴削除エラー: %s",
            error
        )

        return False


# ==========================================
# AI用会話履歴作成
# ==========================================

def build_ai_input(history, user_message):

    messages = []

    for item in history:

        role = item.get("role")
        content = item.get("content")

        if role not in ["user", "assistant"]:
            continue

        if not content:
            continue

        messages.append(
            {
                "role": role,
                "content": content
            }
        )

    messages.append(
        {
            "role": "user",
            "content": user_message
        }
    )

    return messages


# ==========================================
# AI返信生成
# ==========================================

def generate_ai_response(
    history,
    user_message
):

    try:

        messages = build_ai_input(
            history,
            user_message
        )

        response = openai_client.responses.create(
            model=OPENAI_MODEL,
            instructions=SYSTEM_PROMPT,
            input=messages
        )

        answer = response.output_text

        if not answer:
            answer = (
                "ごめん、うまく返事を作れなかった🥲"
            )

        return answer

    except Exception as error:

        logging.exception(
            "OpenAIエラー"
        )

        return (
            "ごめん、今AIが少し調子悪いみたい🥲 "
            "少し時間を置いてもう一度送ってみて！"
        )


# ==========================================
# コマンド処理
# ==========================================

def handle_command(
    user_id,
    message
):

    text = message.strip().lower()

    # --------------------------------------
    # help
    # --------------------------------------

    if text in [
        "/help",
        "help",
        "ヘルプ"
    ]:

        return (
            "🤖 AI会話Bot\n\n"
            "普通にメッセージを送るとAIと会話できます！\n\n"
            "🗑️ /reset\n"
            "会話履歴を削除します"
        )


    # --------------------------------------
    # reset
    # --------------------------------------

    if text in [
        "/reset",
        "reset",
        "リセット"
    ]:

        success = delete_history(
            user_id
        )

        if success:

            return (
                "🗑️ 会話履歴を削除しました！\n"
                "新しい会話を始められます😊"
            )

        return (
            "履歴の削除に失敗しました🥲"
        )


    return None


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
        "X-Line-Signature",
        ""
    )

    # --------------------------------------
    # 署名検証
    # --------------------------------------

    if not validate_signature(
        body,
        signature
    ):

        logging.warning(
            "署名検証失敗"
        )

        abort(400)


    # --------------------------------------
    # JSON取得
    # --------------------------------------

    try:

        data = request.get_json()

    except Exception:

        abort(400)


    events = data.get(
        "events",
        []
    )


    # ======================================
    # イベント処理
    # ======================================

    for event in events:

        # メッセージイベント以外は無視
        if event.get("type") != "message":
            continue


        message = event.get(
            "message",
            {}
        )


        # テキスト以外は無視
        if message.get("type") != "text":
            continue


        # ----------------------------------
        # ユーザー情報
        # ----------------------------------

        source = event.get(
            "source",
            {}
        )

        user_id = source.get(
            "userId"
        )


        if not user_id:
            continue


        # ----------------------------------
        # メッセージ
        # ----------------------------------

        user_message = (
            message.get(
                "text",
                ""
            )
            .strip()
        )


        reply_token = event.get(
            "replyToken"
        )


        if not user_message:
            continue


        logging.info(
            "ユーザー %s: %s",
            user_id,
            user_message
        )


        # ==================================
        # コマンド確認
        # ==================================

        command_response = handle_command(
            user_id,
            user_message
        )


        if command_response:

            reply_message(
                reply_token,
                command_response
            )

            continue


        # ==================================
        # 会話履歴取得
        # ==================================

        history = get_conversation_history(
            user_id,
            limit=10
        )


        # ==================================
        # AI返信生成
        # ==================================

        ai_response = generate_ai_response(
            history,
            user_message
        )


        # ==================================
        # ユーザーメッセージ保存
        # ==================================

        save_message(
            user_id,
            "user",
            user_message
        )


        # ==================================
        # AI返信保存
        # ==================================

        save_message(
            user_id,
            "assistant",
            ai_response
        )


        # ==================================
        # LINE返信
        # ==================================

        reply_message(
            reply_token,
            ai_response
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

    return (
        "LINE AI ChatBot is running!",
        200
    )


# ==========================================
# ヘルスチェック
# ==========================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return jsonify(
        {
            "status": "ok",
            "service": "LINE AI ChatBot"
        }
    )


# ==========================================
# 起動
# ==========================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
