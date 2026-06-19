#!/usr/bin/env python3
"""
Telegram Channel FAQ Bot — Free & Render Web Service ready
Uses Google Gemini (FREE) instead of Anthropic
Uses Webhook instead of polling (required for Render Web Service)

RENDER SETUP:
  Service type: Web Service
  Build command: pip install python-telegram-bot==21.3 google-generativeai flask
  Start command: python bot.py
  Environment Variables:
    TELEGRAM_BOT_TOKEN  → from @BotFather
    GEMINI_API_KEY      → from aistudio.google.com (FREE)
    ADMIN_IDS           → your Telegram numeric ID e.g. 123456789
    RENDER_URL          → your Render URL e.g. https://your-app.onrender.com
"""

import os
import json
import logging
import threading
import google.generativeai as genai
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

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

# Setup Gemini
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

flask_app = Flask(__name__)


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
1. Only answer from the knowledge base. If the answer is not there, say politely that you don't have that info.
2. Always reply in BOTH English AND Arabic — English first, then a divider line ───, then Arabic.
3. Understand questions even with typos or misspellings.
4. Be concise and friendly.

KNOWLEDGE BASE:
{knowledge}

USER QUESTION: {user_question}"""

    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return (
            "❌ Sorry, I couldn't generate an answer right now. Please try again.\n\n"
            "❌ عذرًا، لم أتمكن من إنشاء إجابة الآن. يرجى المحاولة مرة أخرى."
        )


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ────────────────────────────────────────────────────
#  TELEGRAM HANDLERS
# ────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if is_admin(user.id):
        text = (
            "👋 *Welcome, Admin!*\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📬 *Replying to users:*\n"
            "`/answer USER_ID your reply text`\n\n"
            "Example:\n"
            "`/answer 123456789 Yes, we ship worldwide!`\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📋 *FAQ Management:*\n"
            "`/setinfo <text>` — Set channel description\n"
            "`/addqa Q: ... | A: ...` — Add Q&A pair\n"
            "`/listqa` — List all Q&A pairs\n"
            "`/deleteqa <number>` — Delete a Q&A pair\n"
            "`/viewinfo` — View current info\n"
            "`/clearall` — Wipe all FAQ data"
        )
    else:
        text = (
            "👋 *Welcome! / مرحبًا!*\n\n"
            "🤖 I'm the channel assistant.\n"
            "أنا مساعد القناة.\n\n"
            "Just send me your question and I'll answer instantly!\n"
            "فقط أرسل سؤالك وسأجيبك فورًا!\n\n"
            "⬇️ Type your question below!\n"
            "⬇️ اكتب سؤالك أدناه!"
        )
    await update.message.reply_text(text, parse_mode="Markdown")


async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user     = update.effective_user
    chat_id  = update.effective_chat.id
    question = update.message.text.strip()
    if not question:
        return

    await update.message.chat.send_action("typing")
    faq_data  = load_faq()
    ai_answer = ask_gemini(question, faq_data)

    await update.message.reply_text(
        f"🤖 *Answer:*\n\n{ai_answer}\n\n"
        "─────────────────────\n"
        "📌 The admin has also been notified and may send a more detailed answer.\n"
        "📌 تم إخطار المشرف وقد يرسل إجابة أكثر تفصيلاً.",
        parse_mode="Markdown",
    )

    username     = f"@{user.username}" if user.username else user.first_name
    admin_notify = (
        f"📬 *New Question from {username}*\n"
        f"🆔 User ID: `{chat_id}`\n\n"
        f"❓ *Question:*\n{question}\n\n"
        f"─────────────────────\n"
        f"To reply, send:\n"
        f"`/answer {chat_id} your reply here`"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_notify,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Could not notify admin {admin_id}: {e}")


async def admin_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ This command is for admins only.")
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/answer USER_ID your reply`\n\n"
            "Example: `/answer 123456789 Yes, we ship worldwide!`",
            parse_mode="Markdown",
        )
        return
    user_id    = context.args[0]
    reply_text = " ".join(context.args[1:])
    if not user_id.lstrip("-").isdigit():
        await update.message.reply_text("❌ Invalid User ID. It must be a number.")
        return
    try:
        await context.bot.send_message(
            chat_id=int(user_id),
            text=f"✅ *Admin Reply:*\n\n{reply_text}",
            parse_mode="Markdown",
        )
        await update.message.reply_text("✅ Your reply has been sent to the user.")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to send: {e}")


async def set_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/setinfo <channel description>`", parse_mode="Markdown")
        return
    info_text = " ".join(context.args)
    faq_data  = load_faq()
    faq_data["channel_info"] = info_text
    save_faq(faq_data)
    await update.message.reply_text(f"✅ Channel info updated!\n\n{info_text}")


async def add_qa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    full_text = " ".join(context.args)
    if "|" not in full_text or not full_text.lower().startswith("q:"):
        await update.message.reply_text("Usage: `/addqa Q: question | A: answer`", parse_mode="Markdown")
        return
    parts    = full_text.split("|", 1)
    question = parts[0].strip()[2:].strip()
    answer   = parts[1].strip()[2:].strip() if parts[1].strip().lower().startswith("a:") else parts[1].strip()
    if not question or not answer:
        await update.message.reply_text("❌ Both question and answer are required.")
        return
    faq_data = load_faq()
    faq_data["qa_pairs"].append({"question": question, "answer": answer})
    save_faq(faq_data)
    await update.message.reply_text(f"✅ Q&A added!\n\n❓ {question}\n💬 {answer}")


async def list_qa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    faq_data = load_faq()
    pairs    = faq_data.get("qa_pairs", [])
    if not pairs:
        await update.message.reply_text("📭 No Q&A pairs yet. Use /addqa to add some.")
        return
    lines = ["📋 *All Q&A Pairs:*\n"]
    for i, pair in enumerate(pairs, 1):
        lines.append(f"*{i}.* ❓ {pair['question']}\n   💬 {pair['answer']}\n")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def delete_qa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: `/deleteqa <number>`", parse_mode="Markdown")
        return
    index    = int(context.args[0]) - 1
    faq_data = load_faq()
    pairs    = faq_data.get("qa_pairs", [])
    if index < 0 or index >= len(pairs):
        await update.message.reply_text(f"❌ Invalid number. You have {len(pairs)} pairs.")
        return
    removed = pairs.pop(index)
    save_faq(faq_data)
    await update.message.reply_text(f"🗑️ Deleted: {removed['question']}")


async def view_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    faq_data = load_faq()
    info     = faq_data.get("channel_info", "(none set)")
    pairs    = faq_data.get("qa_pairs", [])
    await update.message.reply_text(
        f"📄 *Channel Info:*\n{info}\n\n📋 *Q&A Pairs:* {len(pairs)} total",
        parse_mode="Markdown",
    )


async def clear_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    save_faq({"channel_info": "", "qa_pairs": []})
    await update.message.reply_text("🗑️ All FAQ data cleared.")


# ────────────────────────────────────────────────────
#  WEBHOOK + FLASK (keeps Render Web Service alive)
# ────────────────────────────────────────────────────

application = None


@flask_app.route("/", methods=["GET"])
def index():
    return "✅ Bot is running!", 200


@flask_app.route(f"/webhook", methods=["POST"])
def webhook():
    import asyncio
    update = Update.de_json(request.get_json(force=True), application.bot)
    asyncio.run(application.process_update(update))
    return "ok", 200


async def setup_webhook(app):
    webhook_url = f"{RENDER_URL}/webhook"
    await app.bot.set_webhook(url=webhook_url)
    logger.info(f"✅ Webhook set to {webhook_url}")


def main():
    global application

    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("❌ Set TELEGRAM_BOT_TOKEN environment variable!")
    if not GEMINI_API_KEY:
        raise ValueError("❌ Set GEMINI_API_KEY environment variable!")
    if not ADMIN_IDS:
        raise ValueError("❌ Set ADMIN_IDS environment variable!")
    if not RENDER_URL:
        raise ValueError("❌ Set RENDER_URL environment variable!")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).updater(None).build()

    application.add_handler(CommandHandler("start",     start))
    application.add_handler(CommandHandler("answer",    admin_answer))
    application.add_handler(CommandHandler("setinfo",   set_info))
    application.add_handler(CommandHandler("addqa",     add_qa))
    application.add_handler(CommandHandler("listqa",    list_qa))
    application.add_handler(CommandHandler("deleteqa",  delete_qa))
    application.add_handler(CommandHandler("viewinfo",  view_info))
    application.add_handler(CommandHandler("clearall",  clear_all))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))

    import asyncio
    asyncio.run(setup_webhook(application))

    logger.info(f"✅ Bot running on port {PORT}...")
    flask_app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
