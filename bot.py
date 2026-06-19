#!/usr/bin/env python3
"""
Telegram Channel FAQ Bot — Render-ready
Flow:
  1. User sends question → bot instantly replies with AI answer
  2. Admin gets notified with the question + user ID
  3. Admin replies with /answer USER_ID <text> → bot forwards to user
"""

import os
import json
import logging
import anthropic
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ═══════════════════════════════════════════════════
#  CONFIG — read from environment variables on Render
# ═══════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
# ADMIN_IDS: comma-separated in env, e.g. "123456789,987654321"
ADMIN_IDS = [
    int(x.strip())
    for x in os.environ.get("ADMIN_IDS", "").split(",")
    if x.strip().lstrip("-").isdigit()
]
FAQ_FILE = "/tmp/faq_data.json"   # /tmp is writable on Render
# ═══════════════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ── FAQ storage ──────────────────────────────────────────────────────────────

def load_faq() -> dict:
    if os.path.exists(FAQ_FILE):
        with open(FAQ_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"channel_info": "", "qa_pairs": []}


def save_faq(data: dict) -> None:
    with open(FAQ_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Claude AI answer ─────────────────────────────────────────────────────────

def ask_claude(user_question: str, faq_data: dict) -> str:
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

    system_prompt = f"""You are a helpful FAQ bot for a Telegram channel.
Answer ONLY using the knowledge base below. Do NOT use outside knowledge.

RULES:
1. Only answer from the knowledge base. If the answer is not there, say politely that you don't have that info.
2. Always reply in BOTH English AND Arabic — English first, then a divider line ───, then Arabic.
3. Understand questions even with typos or misspellings.
4. Be concise and friendly.

KNOWLEDGE BASE:
{knowledge}
"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_question}],
        )
        return response.content[0].text
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return (
            "❌ Sorry, I couldn't generate an answer right now. Please try again.\n\n"
            "❌ عذرًا، لم أتمكن من إنشاء إجابة الآن. يرجى المحاولة مرة أخرى."
        )


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ════════════════════════════════════════════════════
#  HANDLERS
# ════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if is_admin(user.id):
        text = (
            "👋 *Welcome, Admin!*\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📬 *Replying to users:*\n"
            "`/answer USER\\_ID your reply text`\n\n"
            "Example:\n"
            "`/answer 123456789 Yes, we ship worldwide!`\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📋 *FAQ Management:*\n"
            "`/setinfo <text>` — Set channel description\n"
            "`/addqa Q: ... | A: ...` — Add Q&A pair\n"
            "`/listqa` — List all Q&A pairs\n"
            "`/deleteqa <number>` — Delete a Q&A pair\n"
            "`/viewinfo` — View current info\n"
            "`/clearall` — Wipe all data"
        )
    else:
        text = (
            "👋 *Welcome\\! / مرحبًا\\!*\n\n"
            "🤖 I'm the channel assistant\\.\n"
            "أنا مساعد القناة\\.\n\n"
            "Just send me your question and I'll answer instantly\\!\n"
            "فقط أرسل سؤالك وسأجيبك فورًا\\!\n\n"
            "⬇️ Type your question below\\!\n"
            "⬇️ اكتب سؤالك أدناه\\!"
        )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User sends a message → instant AI reply + notify admin."""
    user     = update.effective_user
    chat_id  = update.effective_chat.id
    question = update.message.text.strip()

    if not question:
        return

    # 1. Typing indicator + AI answer
    await update.message.chat.send_action("typing")
    faq_data  = load_faq()
    ai_answer = ask_claude(question, faq_data)

    # 2. Send AI answer to user
    await update.message.reply_text(
        f"🤖 *Answer:*\n\n{ai_answer}\n\n"
        "─────────────────────\n"
        "📌 The admin has also been notified and may send a more detailed answer.\n"
        "📌 تم إخطار المشرف وقد يرسل إجابة أكثر تفصيلاً.",
        parse_mode="Markdown",
    )

    # 3. Notify admins
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
    """/answer USER_ID reply text"""
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


# ── FAQ Management ───────────────────────────────────────────────────────────

async def set_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/setinfo <channel description>`", parse_mode="Markdown")
        return
    info_text        = " ".join(context.args)
    faq_data         = load_faq()
    faq_data["channel_info"] = info_text
    save_faq(faq_data)
    await update.message.reply_text(f"✅ Channel info updated!\n\n{info_text}")


async def add_qa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    full_text = " ".join(context.args)
    if "|" not in full_text or not full_text.lower().startswith("q:"):
        await update.message.reply_text(
            "Usage: `/addqa Q: question | A: answer`", parse_mode="Markdown"
        )
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


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set!")
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY environment variable is not set!")
    if not ADMIN_IDS:
        raise ValueError("ADMIN_IDS environment variable is not set!")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("answer",    admin_answer))
    app.add_handler(CommandHandler("setinfo",   set_info))
    app.add_handler(CommandHandler("addqa",     add_qa))
    app.add_handler(CommandHandler("listqa",    list_qa))
    app.add_handler(CommandHandler("deleteqa",  delete_qa))
    app.add_handler(CommandHandler("viewinfo",  view_info))
    app.add_handler(CommandHandler("clearall",  clear_all))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))

    logger.info("✅ Bot is running on Render...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
