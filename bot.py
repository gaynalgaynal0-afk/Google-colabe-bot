#!/usr/bin/env python3
"""
Telegram Channel FAQ Bot — Uses OpenRouter (FREE)
"""

import os
import json
import logging
import asyncio
import httpx
from flask import Flask, request

# ═══════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OPENROUTER_API_KEY  = os.environ.get("OPENROUTER_API_KEY", "")
RENDER_URL          = os.environ.get("RENDER_URL", "").rstrip("/")
ADMIN_IDS = [
    int(x.strip())
    for x in os.environ.get("ADMIN_IDS", "").split(",")
    if x.strip().lstrip("-").isdigit()
]
FAQ_FILE = "/tmp/faq_data.json"
PORT     = int(os.environ.get("PORT", 8080))
TG_API   = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
# ═══════════════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
flask_app = Flask(__name__)


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


# ── FAQ storage ───────────────────────────────────────────────────────────────

def load_faq() -> dict:
    if os.path.exists(FAQ_FILE):
        with open(FAQ_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"channel_info": "", "qa_pairs": []}

def save_faq(data: dict) -> None:
    with open(FAQ_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── OpenRouter AI ─────────────────────────────────────────────────────────────

async def ask_ai(question: str, faq_data: dict) -> str:
    channel_info = faq_data.get("channel_info", "")
    qa_pairs     = faq_data.get("qa_pairs", [])

    if not channel_info and not qa_pairs:
        return (
            "⚠️ No channel information set up yet.\n\n"
            "⚠️ لم يتم إعداد معلومات القناة بعد.\n\n"
            "The admin will answer you soon. / سيجيبك المشرف قريبًا."
        )

    knowledge = ""
    if channel_info:
        knowledge += f"=== Channel Info ===\n{channel_info}\n\n"
    if qa_pairs:
        knowledge += "=== FAQ ===\n"
        for i, p in enumerate(qa_pairs, 1):
            knowledge += f"Q{i}: {p['question']}\nA{i}: {p['answer']}\n\n"

    system = f"""You are a FAQ bot for a Telegram channel.
Answer ONLY from the knowledge base below. Do NOT use outside knowledge.
Reply in BOTH English AND Arabic (English first, then ───, then Arabic).
Understand typos. Be concise and friendly.
If the answer is not in the knowledge base, say politely you don't have that info.

KNOWLEDGE BASE:
{knowledge}"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "mistralai/mistral-7b-instruct:free",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": question},
                    ],
                    "max_tokens": 500,
                },
            )
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"AI error: {e}")
        return (
            "❌ Could not generate answer right now.\n\n"
            "❌ لم أتمكن من إنشاء إجابة الآن."
        )


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
                "🤖 I'm the channel assistant / أنا مساعد القناة\n\n"
                "Send your question and I'll answer instantly!\n"
                "أرسل سؤالك وسأجيبك فورًا!\n\n"
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
        faq = load_faq()
        faq["channel_info"] = info
        save_faq(faq)
        await tg_send(chat_id, f"✅ Channel info updated!\n\n{info}")
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
        faq = load_faq()
        faq["qa_pairs"].append({"question": question, "answer": answer})
        save_faq(faq)
        await tg_send(chat_id, f"✅ Q&A added!\n\n❓ {question}\n💬 {answer}")
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
        idx   = int(parts[1]) - 1
        faq   = load_faq()
        pairs = faq.get("qa_pairs", [])
        if idx < 0 or idx >= len(pairs):
            await tg_send(chat_id, f"❌ Invalid. You have {len(pairs)} pairs.")
            return
        removed = pairs.pop(idx)
        save_faq(faq)
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
        save_faq({"channel_info": "", "qa_pairs": []})
        await tg_send(chat_id, "🗑️ All data cleared.")
        return

    # Regular question
    if not text.startswith("/"):
        await tg_action(chat_id)
        answer = await ask_ai(text, load_faq())
        await tg_send(
            chat_id,
            f"🤖 *Answer:*\n\n{answer}\n\n"
            "─────────────────────\n"
            "📌 Admin notified for a detailed answer.\n"
            "📌 تم إخطار المشرف لإجابة مفصلة.",
        )
        notify = (
            f"📬 *New Question from {uname}*\n"
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
