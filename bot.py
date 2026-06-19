#!/usr/bin/env python3
"""
Telegram Channel FAQ Bot — Free & Render Web Service ready
Uses Google Gemini (FREE) - new google-genai package
Webhook mode for Render Web Service
"""

import os
import json
import logging
import asyncio
import threading
from google import genai
from flask import Flask, request
from telegram import Update, Bot
from telegram.request import HTTPXRequest

# ═══════════════════════════════════════════════════
#  CONFIG — set as environment variables on Render
# ═══════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
RENDER_URL         = os.environ.get("RENDER_URL", "").rstrip("/")
ADMIN_IDS = [
    int(x.strip())
    for x in os.environ.get("ADMIN_IDS", "").split(",")
    if x.strip().lstrip("-").isdigit()
]
FAQ_FILE = "/tmp/faq_data.json"
PORT     = int(os.environ.get("PORT", 8080))
# ═══════════════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

flask_app = Flask(__name__)
bot       = None
gemini_client = None
loop      = None  # persistent asyncio event loop, set up in main()


# ────────────────────────────────────────────────────
#  FAQ STORAGE
# ────────────────────────────────────────────────────

def load_faq() -> dict:
    if os.path.exists(FAQ_FILE):
        with open(FAQ_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"channel_info": "", "qa_pairs": []}


def save_faq(data: dict) -> None:
    with open(FAQ_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ────────────────────────────────────────────────────
#  GEMINI AI ANSWER (FREE)
# ────────────────────────────────────────────────────

def ask_gemini(user_question: str, faq_data: dict) -> str:
    channel_info = faq_data.get("channel_info", "")
    qa_pairs     = faq_data.get("qa_pairs", [])

    if not channel_info and not qa_pairs:
        return (
            "⚠️ No channel information has been set up yet.\n\n"
            "⚠️ لم يتم إعداد معلومات القناة بعد.\n\n"
            "The admin has been notified and will answer you soon.\n"
            "تم إخطار المشرف وسيجيبك قريبًا."
        )

    knowledge = ""
    if channel_info:
        knowledge += f"=== Channel Information ===\n{channel_info}\n\n"
    if qa_pairs:
        knowledge += "=== FAQ ===\n"
        for i, pair in enumerate(qa_pairs, 1):
            knowledge += f"Q{i}: {pair['question']}\nA{i}: {pair['answer']}\n\n"

    prompt = f"""You are a helpful FAQ bot for a Telegram channel.
Answer ONLY using the knowledge base below. Do NOT use outside knowledge.

RULES:
1. Only answer from the knowledge base. If not there, say politely you don't have that info.
2. Always reply in BOTH English AND Arabic — English first, then ───, then Arabic.
3. Understand questions even with typos or misspellings.
4. Be concise and friendly.

KNOWLEDGE BASE:
{knowledge}

USER QUESTION: {user_question}"""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return (
            "❌ Sorry, I couldn't generate an answer right now.\n\n"
            "❌ عذرًا، لم أتمكن من إنشاء إجابة الآن."
        )


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ────────────────────────────────────────────────────
#  PROCESS TELEGRAM UPDATE (no PTB Application)
# ────────────────────────────────────────────────────

async def process_update(update_data: dict) -> None:
    update = Update.de_json(update_data, bot)

    if not update.message or not update.message.text:
        return

    msg      = update.message
    text     = msg.text.strip()
    user     = msg.from_user
    chat_id  = msg.chat_id
    user_id  = user.id

    # ── Commands ──────────────────────────────────────

    if text == "/start":
        if is_admin(user_id):
            reply = (
                "👋 *Welcome, Admin!*\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📬 *Reply to users:*\n"
                "`/answer USER_ID your reply`\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📋 *FAQ Management:*\n"
                "`/setinfo <text>` — Set channel info\n"
                "`/addqa Q: ... | A: ...` — Add Q&A\n"
                "`/listqa` — List Q&A pairs\n"
                "`/deleteqa <number>` — Delete Q&A\n"
                "`/viewinfo` — View info\n"
                "`/clearall` — Clear all data"
            )
        else:
            reply = (
                "👋 *Welcome! / مرحبًا!*\n\n"
                "🤖 I'm the channel assistant.\n"
                "أنا مساعد القناة.\n\n"
                "Send me your question and I'll answer instantly!\n"
                "أرسل سؤالك وسأجيبك فورًا!\n\n"
                "⬇️ Type your question!\n"
                "⬇️ اكتب سؤالك!"
            )
        await bot.send_message(chat_id=chat_id, text=reply, parse_mode="Markdown")
        return

    # ── Admin: /answer USER_ID reply ─────────────────
    if text.startswith("/answer"):
        if not is_admin(user_id):
            await bot.send_message(chat_id=chat_id, text="❌ Admins only.")
            return
        parts = text.split(None, 2)
        if len(parts) < 3:
            await bot.send_message(
                chat_id=chat_id,
                text="Usage: `/answer USER_ID your reply`",
                parse_mode="Markdown",
            )
            return
        target_id  = parts[1]
        reply_text = parts[2]
        if not target_id.lstrip("-").isdigit():
            await bot.send_message(chat_id=chat_id, text="❌ Invalid User ID.")
            return
        try:
            await bot.send_message(
                chat_id=int(target_id),
                text=f"✅ *Admin Reply:*\n\n{reply_text}",
                parse_mode="Markdown",
            )
            await bot.send_message(chat_id=chat_id, text="✅ Reply sent to user.")
        except Exception as e:
            await bot.send_message(chat_id=chat_id, text=f"❌ Failed: {e}")
        return

    # ── Admin: /setinfo ───────────────────────────────
    if text.startswith("/setinfo"):
        if not is_admin(user_id):
            return
        info = text[8:].strip()
        if not info:
            await bot.send_message(chat_id=chat_id, text="Usage: `/setinfo <text>`", parse_mode="Markdown")
            return
        faq = load_faq()
        faq["channel_info"] = info
        save_faq(faq)
        await bot.send_message(chat_id=chat_id, text=f"✅ Channel info updated!\n\n{info}")
        return

    # ── Admin: /addqa ─────────────────────────────────
    if text.startswith("/addqa"):
        if not is_admin(user_id):
            return
        body = text[6:].strip()
        if "|" not in body or not body.lower().startswith("q:"):
            await bot.send_message(chat_id=chat_id, text="Usage: `/addqa Q: question | A: answer`", parse_mode="Markdown")
            return
        parts    = body.split("|", 1)
        question = parts[0].strip()[2:].strip()
        answer   = parts[1].strip()[2:].strip() if parts[1].strip().lower().startswith("a:") else parts[1].strip()
        if not question or not answer:
            await bot.send_message(chat_id=chat_id, text="❌ Both question and answer required.")
            return
        faq = load_faq()
        faq["qa_pairs"].append({"question": question, "answer": answer})
        save_faq(faq)
        await bot.send_message(chat_id=chat_id, text=f"✅ Q&A added!\n\n❓ {question}\n💬 {answer}")
        return

    # ── Admin: /listqa ────────────────────────────────
    if text == "/listqa":
        if not is_admin(user_id):
            return
        faq   = load_faq()
        pairs = faq.get("qa_pairs", [])
        if not pairs:
            await bot.send_message(chat_id=chat_id, text="📭 No Q&A pairs yet.")
            return
        lines = ["📋 *All Q&A Pairs:*\n"]
        for i, pair in enumerate(pairs, 1):
            lines.append(f"*{i}.* ❓ {pair['question']}\n   💬 {pair['answer']}\n")
        await bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="Markdown")
        return

    # ── Admin: /deleteqa ──────────────────────────────
    if text.startswith("/deleteqa"):
        if not is_admin(user_id):
            return
        parts = text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            await bot.send_message(chat_id=chat_id, text="Usage: `/deleteqa <number>`", parse_mode="Markdown")
            return
        index = int(parts[1]) - 1
        faq   = load_faq()
        pairs = faq.get("qa_pairs", [])
        if index < 0 or index >= len(pairs):
            await bot.send_message(chat_id=chat_id, text=f"❌ Invalid number. You have {len(pairs)} pairs.")
            return
        removed = pairs.pop(index)
        save_faq(faq)
        await bot.send_message(chat_id=chat_id, text=f"🗑️ Deleted: {removed['question']}")
        return

    # ── Admin: /viewinfo ──────────────────────────────
    if text == "/viewinfo":
        if not is_admin(user_id):
            return
        faq   = load_faq()
        info  = faq.get("channel_info", "(none set)")
        pairs = faq.get("qa_pairs", [])
        await bot.send_message(
            chat_id=chat_id,
            text=f"📄 *Channel Info:*\n{info}\n\n📋 *Q&A Pairs:* {len(pairs)} total",
            parse_mode="Markdown",
        )
        return

    # ── Admin: /clearall ──────────────────────────────
    if text == "/clearall":
        if not is_admin(user_id):
            return
        save_faq({"channel_info": "", "qa_pairs": []})
        await bot.send_message(chat_id=chat_id, text="🗑️ All FAQ data cleared.")
        return

    # ── Regular user question ─────────────────────────
    if not text.startswith("/"):
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        faq_data  = load_faq()
        ai_answer = ask_gemini(text, faq_data)

        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"🤖 *Answer:*\n\n{ai_answer}\n\n"
                "─────────────────────\n"
                "📌 The admin has also been notified and may send a more detailed answer.\n"
                "📌 تم إخطار المشرف وقد يرسل إجابة أكثر تفصيلاً."
            ),
            parse_mode="Markdown",
        )

        username     = f"@{user.username}" if user.username else user.first_name
        admin_notify = (
            f"📬 *New Question from {username}*\n"
            f"🆔 User ID: `{chat_id}`\n\n"
            f"❓ *Question:*\n{text}\n\n"
            f"─────────────────────\n"
            f"To reply:\n`/answer {chat_id} your reply here`"
        )
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=admin_notify,
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"Could not notify admin {admin_id}: {e}")


# ────────────────────────────────────────────────────
#  FLASK ROUTES
# ────────────────────────────────────────────────────

@flask_app.route("/", methods=["GET"])
def index():
    return "✅ Bot is running!", 200


@flask_app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    # Schedule the coroutine on the single persistent event loop instead of
    # spinning up a new loop (and a new, disconnected HTTPX pool) every call.
    future = asyncio.run_coroutine_threadsafe(process_update(data), loop)
    try:
        future.result(timeout=25)  # don't block Flask forever if Telegram is slow
    except Exception as e:
        logger.error(f"process_update failed: {e}")
    return "ok", 200


# ────────────────────────────────────────────────────
#  MAIN
# ────────────────────────────────────────────────────

def main():
    global bot, gemini_client, loop

    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("❌ Set TELEGRAM_BOT_TOKEN!")
    if not GEMINI_API_KEY:
        raise ValueError("❌ Set GEMINI_API_KEY!")
    if not ADMIN_IDS:
        raise ValueError("❌ Set ADMIN_IDS!")
    if not RENDER_URL:
        raise ValueError("❌ Set RENDER_URL!")

    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

    # Give the bot its own HTTPX request object with a larger connection pool
    # and a sane pool timeout, so a burst of messages doesn't exhaust it.
    request_obj = HTTPXRequest(connection_pool_size=8, pool_timeout=10)
    bot = Bot(token=TELEGRAM_BOT_TOKEN, request=request_obj)

    # Create ONE event loop that lives for the lifetime of the process and
    # run it forever in a background thread. Every webhook call schedules
    # its coroutine onto this same loop via run_coroutine_threadsafe, so the
    # bot's HTTPX connection pool is only ever used from one consistent loop.
    loop = asyncio.new_event_loop()

    def _run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    threading.Thread(target=_run_loop, daemon=True).start()

    async def setup():
        await bot.initialize()
        await bot.set_webhook(url=f"{RENDER_URL}/webhook")
        logger.info(f"✅ Webhook → {RENDER_URL}/webhook")

    asyncio.run_coroutine_threadsafe(setup(), loop).result()

    logger.info(f"✅ Running on port {PORT}")
    flask_app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
