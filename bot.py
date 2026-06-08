import os
import threading
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ── Config ───────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN")
PORT      = int(os.environ.get("PORT", 8080))

bot = telebot.TeleBot(BOT_TOKEN, skip_pending=True)
app = Flask(__name__)

# ── Keyboards ─────────────────────────────────────────────────────────────────
def main_menu_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5406719108123209742">🎬</tg-emoji> Twixtor", callback_data="twixtor"))
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5411197345968701560">🛑</tg-emoji> Hand Brake", callback_data="handbrake"))
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5195033767969839232">⚡</tg-emoji> 120fps Method", callback_data="120fps"))
    return kb

# ── Handlers ──────────────────────────────────────────────────────────────────
@bot.message_handler(commands=["start", "help"])
def start(m):
    bot.send_message(
        m.chat.id,
        "<tg-emoji emoji-id="5406802533567994492">🗂</tg-emoji> <b>Choose your Google Colab Notebook you want to use:</b>",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )

@bot.callback_query_handler(func=lambda c: c.data == "twixtor")
def twixtor(c):
    bot.answer_callback_query(c.id)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5289722755871162900">▶️</tg-emoji> Open Twixtor Notebook", url="https://colab.research.google.com/drive/1kud3m9Rd6YmnDdyQH0xwghWOlFixQcPQ?authuser=2#scrollTo=H3BQmD352fwg"))
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5195033767969839232">🏠</tg-emoji> Menu", callback_data="main_menu"))
    bot.edit_message_text(
        "<tg-emoji emoji-id="5406719108123209742">🎬</tg-emoji> <b>Twixtor Notebook</b>\n\nClick below to open in Chrome:",
        c.message.chat.id, c.message.message_id,
        parse_mode="HTML", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "handbrake")
def handbrake(c):
    bot.answer_callback_query(c.id)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5289722755871162900">▶️</tg-emoji> Open Hand Brake Notebook", url="https://colab.research.google.com/drive/1BaasOwh-Aw7nFL79eGEtc8CDaf_o6wpv?authuser=2#scrollTo=-eI9UIOrc_An"))
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5195033767969839232">🏠</tg-emoji> Menu", callback_data="main_menu"))
    bot.edit_message_text(
        "<tg-emoji emoji-id="5411197345968701560">🛑</tg-emoji> <b>Hand Brake Notebook</b>\n\nClick below to open in Chrome:",
        c.message.chat.id, c.message.message_id,
        parse_mode="HTML", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "120fps")
def fps120(c):
    bot.answer_callback_query(c.id)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5289722755871162900">▶️</tg-emoji> Open 120fps Notebook", url="https://colab.research.google.com/drive/1eWFdpJh9HtCCe0YpBFeNi83Evwq3MLT1?authuser=2#scrollTo=3LMFIE1MUkNK"))
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5195033767969839232">🏠</tg-emoji> Menu", callback_data="main_menu"))
    bot.edit_message_text(
        "<tg-emoji emoji-id="5195033767969839232">⚡</tg-emoji> <b>120fps Method Notebook</b>\n\nClick below to open in Chrome:",
        c.message.chat.id, c.message.message_id,
        parse_mode="HTML", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "main_menu")
def back_to_menu(c):
    bot.answer_callback_query(c.id)
    bot.edit_message_text(
        "<tg-emoji emoji-id="5406802533567994492">🗂</tg-emoji> <b>Choose your Google Colab Notebook you want to use:</b>",
        c.message.chat.id, c.message.message_id,
        parse_mode="HTML", reply_markup=main_menu_kb()
    )

# ── Flask ─────────────────────────────────────────────────────────────────────
@app.route('/')
def home():
    return "Bot is running!"

# ── Run ───────────────────────────────────────────────────────────────────────
def run_bot():
    bot.remove_webhook()
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
    kb.add(InlineKeyboardButton("🏠 Menu", callback_data="main_menu"))
    bot.edit_message_text(
        "🎬 *Twixtor Notebook*\n\nClick below to open in Chrome:",
        c.message.chat.id, c.message.message_id,
        parse_mode="Markdown", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "handbrake")
def handbrake(c):
    bot.answer_callback_query(c.id)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("▶️ Open Hand Brake Notebook", url="https://colab.research.google.com/drive/1BaasOwh-Aw7nFL79eGEtc8CDaf_o6wpv?authuser=2#scrollTo=-eI9UIOrc_An"))
    kb.add(InlineKeyboardButton("🏠 Menu", callback_data="main_menu"))
    bot.edit_message_text(
        "🛑 *Hand Brake Notebook*\n\nClick below to open in Chrome:",
        c.message.chat.id, c.message.message_id,
        parse_mode="Markdown", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "120fps")
def fps120(c):
    bot.answer_callback_query(c.id)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("▶️ Open 120fps Notebook", url="https://colab.research.google.com/drive/1eWFdpJh9HtCCe0YpBFeNi83Evwq3MLT1?authuser=2#scrollTo=3LMFIE1MUkNK"))
    kb.add(InlineKeyboardButton("🏠 Menu", callback_data="main_menu"))
    bot.edit_message_text(
        "⚡ *120fps Method Notebook*\n\nClick below to open in Chrome:",
        c.message.chat.id, c.message.message_id,
        parse_mode="Markdown", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "main_menu")
def back_to_menu(c):
    bot.answer_callback_query(c.id)
    bot.edit_message_text(
        "🗂 *Choose your Google Colab Notebook you want to use:*",
        c.message.chat.id, c.message.message_id,
        parse_mode="Markdown", reply_markup=main_menu_kb()
    )

# ── Flask ─────────────────────────────────────────────────────────────────────
@app.route('/')
def home():
    return "Bot is running!"

# ── Run ───────────────────────────────────────────────────────────────────────
def run_bot():
    bot.remove_webhook()
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
