#!/usr/bin/env python3

import os
import logging
import asyncio
from google import genai
from flask import Flask, request
from telegram import Update, Bot

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
RENDER_URL         = os.environ.get("RENDER_URL", "").rstrip("/")
PORT               = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

flask_app    = Flask(__name__)
bot          = None
gemini_client = None

# Track users waiting to ask a question (after /bot command)
waiting_for_question = set()


def ask_gemini(question: str) -> str:
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=question,
        )
        return response.text
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return "❌ Sorry, couldn't get an answer right now. Try again!"


async def process_update(update_data: dict) -> None:
    update = Update.de_json(update_data, bot)

    if not update.message or not update.message.text:
        return

    msg     = update.message
    text    = msg.text.strip()
    chat_id = msg.chat_id
    user_id = msg.from_user.id if msg.from_user else None
    chat_type = msg.chat.type  # 'private', 'group', 'supergroup', 'channel'

    # ── /bot command (works in channel + private + group) ──
    if text == "/bot" or text.startswith("/bot@"):
        await bot.send_message(
            chat_id=chat_id,
            text="🤖 Tell me your question!",
        )
        if user_id:
            waiting_for_question.add(user_id)
        return

    # ── /start command (private chat only) ──
    if text == "/start" and chat_type == "private":
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "👋 Hello! I'm your AI assistant.\n\n"
                "Just send me any question and I'll answer it instantly! 🚀\n\n"
                "Or use /bot to get started."
            ),
        )
        return

    # ── Regular message in PRIVATE chat → always answer ──
    if chat_type == "private" and not text.startswith("/"):
        if user_id in waiting_for_question:
            waiting_for_question.discard(user_id)

        await bot.send_chat_action(chat_id=chat_id, action="typing")
        answer = ask_gemini(text)
        await bot.send_message(
            chat_id=chat_id,
            text=f"🤖 {answer}",
        )
        return

    # ── Message in CHANNEL/GROUP after /bot command ──
    if chat_type in ("group", "supergroup", "channel") and not text.startswith("/"):
        if user_id and user_id in waiting_for_question:
            waiting_for_question.discard(user_id)
            await bot.send_chat_action(chat_id=chat_id, action="typing")
            answer = ask_gemini(text)
            await bot.send_message(
                chat_id=chat_id,
                text=f"🤖 {answer}",
            )
            return


# ── Flask routes ──

@flask_app.route("/", methods=["GET"])
def index():
    return "✅ Bot is running!", 200


@flask_app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    asyncio.run(process_update(data))
    return "ok", 200


def main():
    global bot, gemini_client

    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("Set TELEGRAM_BOT_TOKEN!")
    if not GEMINI_API_KEY:
        raise ValueError("Set GEMINI_API_KEY!")
    if not RENDER_URL:
        raise ValueError("Set RENDER_URL!")

    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    async def set_webhook():
        await bot.set_webhook(url=f"{RENDER_URL}/webhook")
        logger.info(f"✅ Webhook set → {RENDER_URL}/webhook")

    asyncio.run(set_webhook())

    logger.info(f"✅ Bot running on port {PORT}")
    flask_app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
