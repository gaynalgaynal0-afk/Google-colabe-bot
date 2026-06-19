#!/usr/bin/env python3

import os
import logging
import asyncio
from google import genai
from flask import Flask, request
from telegram import Update, Bot
from telegram.request import HTTPXRequest

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
RENDER_URL         = os.environ.get("RENDER_URL", "").rstrip("/")
PORT               = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

flask_app     = Flask(__name__)
bot           = None
gemini_client = None

waiting_for_question = set()


def ask_gemini(question: str) -> str:
    models_to_try = ["gemini-2.0-flash", "gemini-2.0-flash-001", "gemini-1.5-flash"]
    last_error = None

    for model in models_to_try:
        try:
            logger.info(f"Trying model: {model}")
            response = gemini_client.models.generate_content(
                model=model,
                contents=question,
            )
            if response.text:
                logger.info(f"✅ Got response from {model}")
                return response.text
            else:
                logger.warning(f"Empty response from {model}")
        except Exception as e:
            last_error = e
            logger.error(f"Gemini error with model {model}: {type(e).__name__}: {e}")
            # If it's an auth error, no point trying other models
            error_str = str(e).lower()
            if "api key" in error_str or "permission" in error_str or "unauthorized" in error_str or "authentication" in error_str:
                logger.error("❌ API key issue detected — check your GEMINI_API_KEY environment variable.")
                return "❌ Bot configuration error. Please contact the admin."

    logger.error(f"All models failed. Last error: {last_error}")
    return "❌ Sorry, couldn't get an answer right now. Try again!"


async def process_update(update_data: dict) -> None:
    try:
        update = Update.de_json(update_data, bot)

        msg = update.message or update.channel_post
        if not msg or not msg.text:
            return

        text      = msg.text.strip()
        chat_id   = msg.chat_id
        user_id   = msg.from_user.id if msg.from_user else None
        chat_type = msg.chat.type

        # /bot command
        if text == "/bot" or text.startswith("/bot@"):
            await bot.send_message(chat_id=chat_id, text="🤖 Tell me your question!")
            waiting_for_question.add(user_id if user_id else chat_id)
            return

        # /start in private
        if text == "/start" and chat_type == "private":
            await bot.send_message(
                chat_id=chat_id,
                text="👋 Hello! Just send me any question and I'll answer it instantly! 🚀",
            )
            return

        # Private chat — always answer any message
        if chat_type == "private" and not text.startswith("/"):
            waiting_for_question.discard(user_id)
            answer = ask_gemini(text)
            await bot.send_message(chat_id=chat_id, text=f"🤖 {answer}")
            return

        # Channel / group — answer only after /bot command
        if chat_type in ("group", "supergroup", "channel") and not text.startswith("/"):
            track_key = user_id if user_id else chat_id
            if track_key in waiting_for_question:
                waiting_for_question.discard(track_key)
                answer = ask_gemini(text)
                await bot.send_message(chat_id=chat_id, text=f"🤖 {answer}")
            return

    except Exception as e:
        logger.error(f"process_update error: {e}")


@flask_app.route("/", methods=["GET"])
def index():
    return "✅ Bot is running!", 200


@flask_app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        asyncio.run(process_update(data))
    except Exception as e:
        logger.error(f"Webhook error: {e}")
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

    # Bigger connection pool to fix TimedOut errors
    trequest = HTTPXRequest(connection_pool_size=20, pool_timeout=30)
    bot = Bot(token=TELEGRAM_BOT_TOKEN, request=trequest)

    async def set_webhook():
        await bot.set_webhook(url=f"{RENDER_URL}/webhook")
        logger.info(f"✅ Webhook set → {RENDER_URL}/webhook")

    asyncio.run(set_webhook())

    logger.info(f"✅ Bot running on port {PORT}")
    flask_app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
