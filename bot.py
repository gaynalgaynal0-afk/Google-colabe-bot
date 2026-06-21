#!/usr/bin/env python3
"""
Telegram Channel FAQ Bot — Permanent Database Storage (Supabase)
"""

import os
import json
import logging
import asyncio
import httpx
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request

# ═══════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
RENDER_URL         = os.environ.get("RENDER_URL", "").rstrip("/")
DATABASE_URL       = os.environ.get("DATABASE_URL", "")
ADMIN_IDS = [
    int(x.strip())
    for x in os.environ.get("ADMIN_IDS", "").split(",")
    if x.strip().lstrip("-").isdigit()
]
PORT   = int(os.environ.get("PORT", 8080))
TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
# ═══════════════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
flask_app = Flask(__name__)


# ── Database ──────────────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    """Create tables if they don't exist."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS faq_config (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS qa_pairs (
                    id       SERIAL PRIMARY KEY,
                    question TEXT NOT NULL,
                    answer   TEXT NOT NULL
                );
            """)
        conn.commit()
    logger.info("✅ Database initialized")

def load_faq() -> dict:
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT value FROM faq_config WHERE key = 'channel_info'")
                row = cur.fetchone()
                channel_info = row["value"] if row else ""

                cur.execute("SELECT question, answer FROM qa_pairs ORDER BY id")
                pairs = [{"question": r["question"], "answer": r["answer"]} for r in cur.fetchall()]

        return {"channel_info": channel_info, "qa_pairs": pairs}
    except Exception as e:
        logger.error(f"load_faq error: {e}")
        return {"channel_info": "", "qa_pairs": []}

def save_channel_info(info: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO faq_config (key, value)
                VALUES ('channel_info', %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """, (info,))
        conn.commit()

def add_qa(question: str, answer: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO qa_pairs (question, answer) VALUES (%s, %s)",
                (question, answer)
            )
        conn.commit()

def delete_qa(index: int) -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, question FROM qa_pairs ORDER BY id")
            rows = cur.fetchall()
            if index < 0 or index >= len(rows):
                return None
            row_id = rows[index]["id"]
            question = rows[index]["question"]
            cur.execute("DELETE FROM qa_pairs WHERE id = %s", (row_id,))
        conn.commit()
    return {"question": question}

def clear_all_faq():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM qa_pairs")
            cur.execute("DELETE FROM faq_config WHERE key = 'channel_info'")
        conn.commit()


# ── Telegram helpers ──────────────────────────────────────────────────────────

async def tg_send(chat_id: int, text: str, parse_mode: str = "Markdown") -> None:
    if len(text) > 4000:
        text = text[:4000] + "..."
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{TG_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        })
        if r.status_code != 200:
            logger.error(f"tg_send failed: {r.text}")

async def tg_action(chat_id: int) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{TG_API}/sendChatAction", json={
            "chat_id": chat_id, "action": "typing"
        })

async def tg_set_webhook(url: str) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{TG_API}/setWebhook", json={
            "url": url,
            "allowed_updates": ["message"],
        })
        logger.info(f"✅ Webhook → {r.json()}")


# ── AI ────────────────────────────────────────────────────────────────────────

async def ask_ai(question: str, faq_data: dict) -> str:
    channel_info = faq_data.get("channel_info", "")
    qa_pairs     = faq_data.get("qa_pairs", [])

    channel_knowledge = ""
    if channel_info:
        channel_knowledge += f"=== Channel Info ===\n{channel_info}\n\n"
    if qa_pairs:
        channel_knowledge += "=== Channel FAQ ===\n"
        for i, p in enumerate(qa_pairs, 1):
            channel_knowledge += f"Q{i}: {p['question']}\nA{i}: {p['answer']}\n\n"

    if channel_knowledge:
        system = f"""You are a smart AI assistant for a Telegram channel.
You can answer ANY question the user asks like a real AI.
You also have special knowledge about this channel — if the question is related to the channel, prioritize that info.

CHANNEL KNOWLEDGE:
{channel_knowledge}

RULES:
- Answer any question helpfully and accurately
- If the question is about the channel, use the channel knowledge above
- Always reply in BOTH English AND Arabic (English first, then ───, then Arabic)
- Be friendly, concise and helpful
- Understand typos and misspellings"""
    else:
        system = """You are a smart AI assistant for a Telegram channel.
Answer any question helpfully and accurately.
Always reply in BOTH English AND Arabic (English first, then ───, then Arabic).
Be friendly, concise and helpful. Understand typos and misspellings."""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "openai/gpt-oss-120b:free",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": question},
                    ],
                    "max_tokens": 600,
                },
            )
            data = r.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"].strip()
            else:
                logger.error(f"Unexpected response: {data}")
                return "❌ Could not generate answer.\n\n❌ لم أتمكن من إنشاء إجابة."
    except Exception as e:
        logger.error(f"AI error: {e}")
        return "❌ Could not generate answer.\n\n❌ لم أتمكن من إنشاء إجابة."


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# ── Update handler ────────────────────────────────────────────────────────────

async def handle(data: dict) -> None:
    logger.info(f"Update: {json.dumps(data)[:200]}")

    msg = data.get("message")
    if not msg or not msg.get("text"):
        return

    text      = msg["text"].strip()
    chat_id   = msg["chat"]["id"]
    chat_type = msg["chat"].get("type", "private")
    user      = msg.get("from", {})
    uid       = user.get("id", 0)
    uname     = f"@{user['username']}" if user.get("username") else user.get("first_name", "User")

    logger.info(f"{uname} in {chat_type}: {text}")

    # /start
    if text.startswith("/start"):
        if is_admin(uid):
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
                "`/viewinfo` — View current info\n"
                "`/clearall` — Clear all data"
            )
        else:
            reply = (
                "👋 *Welcome! / مرحبًا!*\n\n"
                "🤖 I'm a smart AI assistant for this channel!\n"
                "أنا مساعد ذكاء اصطناعي لهذه القناة!\n\n"
                "Ask me *anything* — I can answer any question!\n"
                "اسألني *أي شيء* — يمكنني الإجابة على أي سؤال!\n\n"
                "⬇️ Type your question / اكتب سؤالك"
            )
        await tg_send(chat_id, reply)
        return

    # /answer
    if text.startswith("/answer"):
        if not is_admin(uid): return
        parts = text.split(None, 2)
        if len(parts) < 3 or not parts[1].lstrip("-").isdigit():
            await tg_send(chat_id, "Usage: `/answer USER_ID your reply`")
            return
        try:
            await tg_send(int(parts[1]), f"✅ *Admin Reply:*\n\n{parts[2]}")
            await tg_send(chat_id, "✅ Reply sent!")
        except Exception as e:
            await tg_send(chat_id, f"❌ Failed: {e}")
        return

    # /setinfo
    if text.startswith("/setinfo"):
        if not is_admin(uid): return
        info = text[8:].strip()
        if not info:
            await tg_send(chat_id, "Usage: `/setinfo <description>`")
            return
        save_channel_info(info)
        await tg_send(chat_id, f"✅ Channel info saved permanently!\n\n{info}")
        return

    # /addqa
    if text.startswith("/addqa"):
        if not is_admin(uid): return
        body = text[6:].strip()
        if "|" not in body or not body.lower().startswith("q:"):
            await tg_send(chat_id, "Usage: `/addqa Q: question | A: answer`")
            return
        parts    = body.split("|", 1)
        question = parts[0].strip()[2:].strip()
        answer   = parts[1].strip()[2:].strip() if parts[1].strip().lower().startswith("a:") else parts[1].strip()
        if not question or not answer:
            await tg_send(chat_id, "❌ Both question and answer required.")
            return
        add_qa(question, answer)
        await tg_send(chat_id, f"✅ Q&A saved permanently!\n\n❓ {question}\n💬 {answer}")
        return

    # /listqa
    if text == "/listqa":
        if not is_admin(uid): return
        faq   = load_faq()
        pairs = faq.get("qa_pairs", [])
        if not pairs:
            await tg_send(chat_id, "📭 No Q&A pairs yet.")
            return
        lines = ["📋 *All Q&A Pairs:*\n"]
        for i, p in enumerate(pairs, 1):
            lines.append(f"*{i}.* ❓ {p['question']}\n   💬 {p['answer']}\n")
        await tg_send(chat_id, "\n".join(lines))
        return

    # /deleteqa
    if text.startswith("/deleteqa"):
        if not is_admin(uid): return
        parts = text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            await tg_send(chat_id, "Usage: `/deleteqa <number>`")
            return
        removed = delete_qa(int(parts[1]) - 1)
        if not removed:
            faq = load_faq()
            await tg_send(chat_id, f"❌ Invalid number. You have {len(faq['qa_pairs'])} pairs.")
            return
        await tg_send(chat_id, f"🗑️ Deleted: {removed['question']}")
        return

    # /viewinfo
    if text == "/viewinfo":
        if not is_admin(uid): return
        faq   = load_faq()
        info  = faq.get("channel_info", "(none set)")
        pairs = faq.get("qa_pairs", [])
        await tg_send(chat_id, f"📄 *Channel Info:*\n{info}\n\n📋 *Q&A Pairs:* {len(pairs)} total")
        return

    # /clearall
    if text == "/clearall":
        if not is_admin(uid): return
        clear_all_faq()
        await tg_send(chat_id, "🗑️ All data cleared from database.")
        return

    # Any message → full AI answer
    if not text.startswith("/"):
        await tg_action(chat_id)
        answer = await ask_ai(text, load_faq())
        await tg_send(chat_id, f"🤖 {answer}")

        notify = (
            f"📬 *New Message from {uname}*\n"
            f"🆔 User ID: `{chat_id}`\n"
            f"💬 Chat: `{chat_type}`\n\n"
            f"❓ *Question:*\n{text}\n\n"
            f"Reply: `/answer {chat_id} your reply`"
        )
        for aid in ADMIN_IDS:
            try:
                await tg_send(aid, notify)
            except Exception as e:
                logger.error(f"Admin notify failed: {e}")


# ── Flask ─────────────────────────────────────────────────────────────────────

@flask_app.route("/", methods=["GET"])
def index():
    return "✅ Bot is running!", 200

@flask_app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(handle(data))
    except Exception as e:
        logger.error(f"Webhook error: {e}")
    finally:
        loop.close()
    return "ok", 200


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    missing = [k for k, v in {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OPENROUTER_API_KEY": OPENROUTER_API_KEY,
        "RENDER_URL":         RENDER_URL,
        "DATABASE_URL":       DATABASE_URL,
    }.items() if not v]
    if missing:
        raise ValueError(f"❌ Missing: {', '.join(missing)}")
    if not ADMIN_IDS:
        raise ValueError("❌ Set ADMIN_IDS!")

    init_db()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(tg_set_webhook(f"{RENDER_URL}/webhook"))
    loop.close()

    logger.info(f"✅ Bot running on port {PORT}")
    flask_app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
