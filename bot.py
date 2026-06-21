#!/usr/bin/env python3
"""
Telegram Channel FAQ Bot — JSONBin.io permanent storage (FREE)
"""

import os
import json
import logging
import asyncio
import httpx
from flask import Flask, request

# ═══════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
RENDER_URL         = os.environ.get("RENDER_URL", "").rstrip("/")
JSONBIN_KEY        = os.environ.get("JSONBIN_KEY", "")
JSONBIN_BIN_ID     = os.environ.get("JSONBIN_BIN_ID", "")  # set after first run
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

JSONBIN_URL = "https://api.jsonbin.io/v3"
DEFAULT_FAQ = {"channel_info": "", "qa_pairs": []}


# ── JSONBin storage ───────────────────────────────────────────────────────────

async def jsonbin_read() -> dict:
    bin_id = os.environ.get("JSONBIN_BIN_ID", "")
    if not bin_id:
        return DEFAULT_FAQ.copy()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{JSONBIN_URL}/b/{bin_id}/latest",
            headers={"X-Master-Key": JSONBIN_KEY},
        )
        if r.status_code == 200:
            return r.json().get("record", DEFAULT_FAQ.copy())
        logger.error(f"JSONBin read error: {r.text}")
        return DEFAULT_FAQ.copy()


async def jsonbin_write(data: dict) -> bool:
    bin_id = os.environ.get("JSONBIN_BIN_ID", "")
    if not bin_id:
        # Create a new bin
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{JSONBIN_URL}/b",
                headers={
                    "X-Master-Key": JSONBIN_KEY,
                    "Content-Type": "application/json",
                    "X-Bin-Name": "faq-bot-data",
                    "X-Bin-Private": "true",
                },
                json=data,
            )
            if r.status_code == 200:
                new_id = r.json()["metadata"]["id"]
                os.environ["JSONBIN_BIN_ID"] = new_id
                logger.info(f"✅ Created JSONBin with ID: {new_id}")
                logger.info(f"⚠️  Add JSONBIN_BIN_ID={new_id} to Render env vars!")
                return True
            logger.error(f"JSONBin create error: {r.text}")
            return False
    else:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.put(
                f"{JSONBIN_URL}/b/{bin_id}",
                headers={
                    "X-Master-Key": JSONBIN_KEY,
                    "Content-Type": "application/json",
                },
                json=data,
            )
            if r.status_code == 200:
                return True
            logger.error(f"JSONBin write error: {r.text}")
            return False


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
            logger.error(f"AI bad response: {data}")
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
        faq = await jsonbin_read()
        faq["channel_info"] = info
        await jsonbin_write(faq)
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
        faq = await jsonbin_read()
        faq["qa_pairs"].append({"question": question, "answer": answer})
        await jsonbin_write(faq)
        await tg_send(chat_id, f"✅ Q&A saved permanently!\n\n❓ {question}\n💬 {answer}")
        return

    # /listqa
    if text == "/listqa":
        if not is_admin(uid): return
        faq   = await jsonbin_read()
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
        idx   = int(parts[1]) - 1
        faq   = await jsonbin_read()
        pairs = faq.get("qa_pairs", [])
        if idx < 0 or idx >= len(pairs):
            await tg_send(chat_id, f"❌ Invalid. You have {len(pairs)} pairs.")
            return
        removed = pairs.pop(idx)
        await jsonbin_write(faq)
        await tg_send(chat_id, f"🗑️ Deleted: {removed['question']}")
        return

    # /viewinfo
    if text == "/viewinfo":
        if not is_admin(uid): return
        faq   = await jsonbin_read()
        info  = faq.get("channel_info", "(none set)")
        pairs = faq.get("qa_pairs", [])
        await tg_send(chat_id, f"📄 *Channel Info:*\n{info}\n\n📋 *Q&A Pairs:* {len(pairs)} total")
        return

    # /clearall
    if text == "/clearall":
        if not is_admin(uid): return
        await jsonbin_write(DEFAULT_FAQ.copy())
        await tg_send(chat_id, "🗑️ All data cleared.")
        return

    # Any message → full AI answer
    if not text.startswith("/"):
        await tg_action(chat_id)
        faq    = await jsonbin_read()
        answer = await ask_ai(text, faq)
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
        "JSONBIN_KEY":        JSONBIN_KEY,
    }.items() if not v]
    if missing:
        raise ValueError(f"❌ Missing: {', '.join(missing)}")
    if not ADMIN_IDS:
        raise ValueError("❌ Set ADMIN_IDS!")

    loop = asyncio.new_event_loop()
    loop.run_until_complete(tg_set_webhook(f"{RENDER_URL}/webhook"))
    loop.close()

    logger.info(f"✅ Bot running on port {PORT}")
    flask_app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
