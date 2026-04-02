from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, CommandHandler, CallbackQueryHandler, filters
import sqlite3
import os
import string
from datetime import datetime
import shutil
import asyncio

TOKEN = os.environ.get("TOKENOTVET")
BACKUP_ADMIN_ID = 866973179  # сюда будет отправляться бэкап

# ---------------- SQLite ----------------
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
    cursor.execute("SELECT counter FROM counters WHERE chat_id=?", (chat_id,))
    row = cursor.fetchone()
    if row:
        number = row[0] + 1
        cursor.execute("UPDATE counters SET counter=? WHERE chat_id=?", (number, chat_id))
    else:
        number = 1
        cursor.execute("INSERT INTO counters (chat_id, counter) VALUES (?, ?)", (chat_id, number))
    conn.commit()
    return number

# ---------------- Магазины ----------------
SHOPS = {
    -1003450185997: {"address": "📍 Наш адрес: Майкоп, ул. Строителей 8Б", "work_time": "🕒 10:00–19:00", "max_link": "https://max.ru/join/IMHKjeOxfKJFcRQTQVrhlCGvLx-qOzAUiTpxCussSr0"},
    -1003777692701: {"address": "📍 Майкоп, ул. Депутатская 16Б", "work_time": "🕒 10:00–19:00", "max_link": "https://max.ru/join/WZ8T-qgVdTK7He20c2UAvDcawKYbedKxKFmKVZbWovo"},
    -1003840431977: {"address": "📍 Лабинск, ул. Победы 161", "work_time": "🕒 09:00–18:00", "max_link": "https://max.ru/join/caMNU_JQa9Q1-UlwqS1r6G9AECURkQn0ARdLGtM25wI"}
}

BLACKLIST_LINKS = ["https://max.ru/join"]
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

async def backup_db(context: ContextTypes.DEFAULT_TYPE = None):
    """Сохраняем резерв и отправляем администратору"""
    backup_file = "tickets_backup.db"
    shutil.copyfile(DB_FILE, backup_file)
    if context:
        try:
            await context.bot.send_document(
                chat_id=BACKUP_ADMIN_ID,
                document=open(backup_file, "rb"),
                filename=backup_file
            )
        except Exception as e:
            print("Ошибка при отправке бэкапа:", e)

# ---------------- Команды ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Чат активен, приятных покупок 🎉")

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    text = "📅 Сегодняшние участники:\n\n"
    for chat_id, name in REVIEW_CHATS.items():
        cursor.execute("SELECT number, user_id FROM tickets WHERE chat_id=? AND date=? ORDER BY number", (str(chat_id), today_str))
        rows = cursor.fetchall()
        text += f"{name}\n"
        if not rows:
            text += "нет участников\n\n"
            continue
        for number, user_id in rows:
            user_link = f"https://t.me/user?id={user_id}"
            text += f"#{number} — {user_link}\n"
        text += "\n"
    await update.message.reply_text(text)

async def data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await update.message.reply_document(document=open(DB_FILE, "rb"), filename="tickets.db")

async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.lower()
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    if chat_id not in REVIEW_CHATS or REVIEW_HASHTAG not in text or is_blacklisted_link(text):
        return
    cursor.execute("SELECT 1 FROM tickets WHERE chat_id=? AND user_id=? AND date=?", (str(chat_id), user_id, today_str))
    if cursor.fetchone():
        return
    number = get_next_number(str(chat_id))
    message_id = update.message.message_id
    chat_username = update.effective_chat.username
    if chat_username:
        link = f"https://t.me/{chat_username}/{message_id}"
    else:
        chat_id_clean = str(chat_id).replace("-100", "")
        link = f"https://t.me/c/{chat_id_clean}/{message_id}"
    cursor.execute("INSERT INTO tickets (chat_id, user_id, number, date, link) VALUES (?, ?, ?, ?, ?)", (str(chat_id), user_id, number, today_str, link))
    conn.commit()
    try:
        await context.bot.send_message(chat_id=int(user_id), text=f"🎟 Ваш номер участника: #{number}")
    except:
        pass
    # асинхронно создаем бэкап
    asyncio.create_task(backup_db(context))

async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    text = "📊 Статистика\n\n"
    for chat_id, name in REVIEW_CHATS.items():
        cursor.execute("SELECT COUNT(*) FROM tickets WHERE chat_id=? AND date=?", (str(chat_id), today_str))
        today_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tickets WHERE chat_id=?", (str(chat_id),))
        total = cursor.fetchone()[0]
        text += f"{name}\nСегодня: {today_count}\nВсего: {total}\n\n"
    await update.message.reply_text(text)

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("/check номер билета")
        return
    number = int(context.args[0])
    cursor.execute("SELECT user_id, date, link FROM tickets WHERE number=?", (number,))
    row = cursor.fetchone()
    if row:
        user_link = f"https://t.me/user?id={row[0]}"
        await update.message.reply_text(f"🎟 Номер: {number}\n👤 User: {user_link}\n📅 {row[1]}\n🔗 {row[2]}")
    else:
        await update.message.reply_text("Не найден")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    keyboard = [[InlineKeyboardButton("✅ Да", callback_data="reset_yes"), InlineKeyboardButton("❌ Нет", callback_data="reset_no")]]
    await update.message.reply_text("Сбросить розыгрыш?", reply_markup=InlineKeyboardMarkup(keyboard))

async def reset_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "reset_yes":
        cursor.execute("DELETE FROM tickets")
        cursor.execute("DELETE FROM counters")
        conn.commit()
        await query.edit_message_text("Розыгрыш сброшен")
        asyncio.create_task(backup_db(context))
    else:
        await query.edit_message_text("Отмена")

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