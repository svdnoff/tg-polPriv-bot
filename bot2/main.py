from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, CommandHandler, CallbackQueryHandler, filters
import sqlite3
import os
import string
import re
from rapidfuzz import fuzz
from datetime import datetime

TOKEN = os.environ.get("TOKENOTVET")

# ---------------- База SQLite ----------------
DB_FILE = "tickets.db"

conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT,
    user_id TEXT,
    number INTEGER,
    date TEXT,
    link TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS counters (
    chat_id TEXT PRIMARY KEY,
    counter INTEGER
)
""")

conn.commit()

def get_next_number(chat_id):
    cursor.execute(
        "SELECT counter FROM counters WHERE chat_id=?",
        (chat_id,)
    )
    row = cursor.fetchone()

    if row:
        number = row[0] + 1
        cursor.execute(
            "UPDATE counters SET counter=? WHERE chat_id=?",
            (number, chat_id)
        )
    else:
        number = 1
        cursor.execute(
            "INSERT INTO counters (chat_id, counter) VALUES (?, ?)",
            (chat_id, number)
        )

    conn.commit()
    return number


# ---------------- Магазины ----------------
SHOPS = {
    -1003450185997: {
        "address": "📍 Наш адрес: Майкоп, ул. Строителей 8Б (район железного рынка)",
        "work_time": "🕒 Мы работаем: 10:00–19:00 каждый день!",
        "max_link": "📱 Мы есть в MAX: https://max.ru/join/IMHKjeOxfKJFcRQTQVrhlCGvLx-qOzAUiTpxCussSr0"
    },
    -1003777692701: {
        "address": "📍 Наш адрес: Майкоп, ул. Депутатская 16Б",
        "work_time": "🕒 Мы работаем: 10:00–19:00 каждый день!",
        "max_link": "📱 Мы есть в MAX: https://max.ru/join/WZ8T-qgVdTK7He20c2UAvDcawKYbedKxKFmKVZbWovo"
    },
    -1003840431977: {
        "address": "📍 Наш адрес: Лабинск, ул. Победы 161",
        "work_time": "🕒 Мы работаем: 09:00–18:00 каждый день!",
        "max_link": "📱 Мы есть в MAX: https://max.ru/join/caMNU_JQa9Q1-UlwqS1r6G9AECURkQn0ARdLGtM25wI"
    }
}

BLACKLIST_LINKS = ["https://max.ru/join"]
THRESHOLD = 85

REVIEW_HASHTAG = "#отзыв"

REVIEW_CHATS = {
    -1003450185997: "Майкоп Строителей",
    -1003777692701: "Майкоп Депутатская",
    -1003840431977: "Лабинск"
}

ADMIN_IDS = [1014380197, 866973179]

# ---------------- Вспомогательные ----------------
def clean(text: str) -> str:
    return text.lower().translate(str.maketrans('', '', string.punctuation)).strip()

def is_blacklisted_link(text: str) -> bool:
    return any(link in text for link in BLACKLIST_LINKS)

# ---------------- start ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Чат активен, приятных покупок 🎉")

# ---------------- #отзыв ----------------
async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    today = datetime.utcnow().strftime("%Y-%m-%d")

    text = "📅 Сегодняшние участники:\n\n"

    for chat_id, name in REVIEW_CHATS.items():
        cursor.execute("""
        SELECT number, user_id 
        FROM tickets 
        WHERE chat_id=? AND date=?
        ORDER BY number
        """, (str(chat_id), today))

        rows = cursor.fetchall()

        text += f"{name}\n"

        if not rows:
            text += "нет участников\n\n"
            continue

        for number, user in rows:
            text += f"#{number} — {user}\n"

        text += "\n"

    await update.message.reply_text(text)

async def data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    await update.message.reply_document(
        document=open(DB_FILE, "rb"),
        filename="tickets.db"
    )

async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.lower()
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = str(user.id)
    today = datetime.utcnow().strftime("%Y-%m-%d")

    if chat_id not in REVIEW_CHATS:
        return

    if REVIEW_HASHTAG not in text:
        return

    if is_blacklisted_link(text):
        return

    chat_id_str = str(chat_id)

    # проверка уже участвовал сегодня
    cursor.execute("""
    SELECT 1 FROM tickets 
    WHERE chat_id=? AND user_id=? AND date=?
    """, (chat_id_str, user_id, today))

    if cursor.fetchone():
        return

    number = get_next_number(chat_id_str)

    message_id = update.message.message_id
    chat_username = update.effective_chat.username

    if chat_username:
        link = f"https://t.me/{chat_username}/{message_id}"
    else:
        chat_id_clean = str(chat_id).replace("-100", "")
        link = f"https://t.me/c/{chat_id_clean}/{message_id}"

    cursor.execute("""
    INSERT INTO tickets (chat_id, user_id, number, date, link)
    VALUES (?, ?, ?, ?, ?)
    """, (chat_id_str, user_id, number, today, link))

    conn.commit()

    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=f"🎟 Ваш номер участника: #{number}"
        )
    except:
        pass

# ---------------- stat ----------------
async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    today = datetime.utcnow().strftime("%Y-%m-%d")
    text = "📊 Статистика\n\n"

    for chat_id, name in REVIEW_CHATS.items():
        cursor.execute("""
        SELECT COUNT(*) FROM tickets WHERE chat_id=? AND date=?
        """, (str(chat_id), today))
        today_count = cursor.fetchone()[0]

        cursor.execute("""
        SELECT COUNT(*) FROM tickets WHERE chat_id=?
        """, (str(chat_id),))
        total = cursor.fetchone()[0]

        text += f"{name}\nСегодня: {today_count}\nВсего: {total}\n\n"

    await update.message.reply_text(text)

# ---------------- check ----------------
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    if not context.args:
        await update.message.reply_text("/check 27")
        return

    number = int(context.args[0])

    cursor.execute("""
    SELECT user_id, date, link 
    FROM tickets 
    WHERE number=?
    """, (number,))

    row = cursor.fetchone()

    if row:
        await update.message.reply_text(
            f"🎟 Номер: {number}\n"
            f"👤 User ID: {row[0]}\n"
            f"📅 {row[1]}\n"
            f"🔗 {row[2]}"
        )
    else:
        await update.message.reply_text("Не найден")

# ---------------- reset ----------------
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    keyboard = [[
        InlineKeyboardButton("✅ Да", callback_data="reset_yes"),
        InlineKeyboardButton("❌ Нет", callback_data="reset_no")
    ]]

    await update.message.reply_text(
        "Сбросить розыгрыш?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def reset_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "reset_yes":
        cursor.execute("DELETE FROM tickets")
        cursor.execute("DELETE FROM counters")
        conn.commit()
        await query.edit_message_text("Розыгрыш сброшен")
    else:
        await query.edit_message_text("Отмена")

# ---------------- ID ----------------
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(str(update.effective_chat.id))

# ---------------- запуск ----------------
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stat", stat))
app.add_handler(CommandHandler("check", check))
app.add_handler(CommandHandler("reset", reset))
app.add_handler(CommandHandler("id", get_id))
app.add_handler(CommandHandler("today", today))
app.add_handler(CommandHandler("data", data))

app.add_handler(CallbackQueryHandler(reset_confirm))

app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_review))

app.run_polling()