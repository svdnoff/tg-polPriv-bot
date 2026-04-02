import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

# -------------------- Настройки --------------------
TOKEN = os.environ.get("TOKENOTVET")  # токен бота
DB_URL = "postgresql://postgres:[YOUR-PASSWORD]@db.qdxrkryvpnglbqpugdoh.supabase.co:5432/postgres"

ADMIN_IDS = [1014380197, 866973179]

REVIEW_HASHTAG = "#отзыв"
REVIEW_CHATS = {
    -1003450185997: "Майкоп Строителей",
    -1003777692701: "Майкоп Депутатская",
    -1003840431977: "Лабинск"
}

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
ADDRESS_KEYWORDS = ["адрес", "где найти", "где приехать", "как найти", "где вы"]
WORK_KEYWORDS = ["время работы", "работаете", "до скольки", "график работы"]
MAX_KEYWORDS = ["max", "макс", "в максе", "есть ли макс", "ссылка на макс"]

# -------------------- Подключение к PostgreSQL --------------------
conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
cursor = conn.cursor()

# создаем таблицы если нет
cursor.execute("""
CREATE TABLE IF NOT EXISTS tickets (
    id SERIAL PRIMARY KEY,
    chat_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    number INTEGER NOT NULL,
    date DATE NOT NULL,
    link TEXT NOT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS counters (
    chat_id TEXT PRIMARY KEY,
    counter INTEGER NOT NULL
)
""")
conn.commit()

# -------------------- Вспомогательные функции --------------------
def clean(text: str) -> str:
    return text.lower().strip()

def is_blacklisted_link(text: str) -> bool:
    return any(link in text for link in BLACKLIST_LINKS)

def get_next_number(chat_id):
    cursor.execute("SELECT counter FROM counters WHERE chat_id=%s", (chat_id,))
    row = cursor.fetchone()
    if row:
        number = row["counter"] + 1
        cursor.execute("UPDATE counters SET counter=%s WHERE chat_id=%s", (number, chat_id))
    else:
        number = 1
        cursor.execute("INSERT INTO counters (chat_id, counter) VALUES (%s, %s)", (chat_id, number))
    conn.commit()
    return number

# -------------------- Команды --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Чат активен, приятных покупок 🎉")

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(str(update.effective_chat.id))

# -------------------- Обработка отзывов --------------------
async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.lower()
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    today = datetime.utcnow().strftime("%Y-%m-%d")

    if chat_id not in REVIEW_CHATS:
        return
    if REVIEW_HASHTAG not in text:
        return
    if is_blacklisted_link(text):
        return

    # проверка участия сегодня
    cursor.execute("SELECT 1 FROM tickets WHERE chat_id=%s AND user_id=%s AND date=%s", (str(chat_id), user_id, today))
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

    cursor.execute("""
    INSERT INTO tickets (chat_id, user_id, number, date, link)
    VALUES (%s, %s, %s, %s, %s)
    """, (str(chat_id), user_id, number, today, link))
    conn.commit()

    try:
        await context.bot.send_message(chat_id=update.effective_user.id, text=f"🎟 Ваш номер участника: #{number}")
    except:
        pass

# -------------------- Статистика --------------------
async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    today = datetime.utcnow().strftime("%Y-%m-%d")
    text = "📊 Статистика\n\n"
    for chat_id, name in REVIEW_CHATS.items():
        cursor.execute("SELECT COUNT(*) FROM tickets WHERE chat_id=%s AND date=%s", (str(chat_id), today))
        today_count = cursor.fetchone()["count"]
        cursor.execute("SELECT COUNT(*) FROM tickets WHERE chat_id=%s", (str(chat_id),))
        total = cursor.fetchone()["count"]
        text += f"{name}\nСегодня: {today_count}\nВсего: {total}\n\n"
    await update.message.reply_text(text)

# -------------------- /today --------------------
async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    text = "📅 Сегодняшние участники:\n\n"
    for chat_id, name in REVIEW_CHATS.items():
        cursor.execute("SELECT number, user_id FROM tickets WHERE chat_id=%s AND date=%s ORDER BY number", (str(chat_id), today_str))
        rows = cursor.fetchall()
        text += f"{name}\n"
        if not rows:
            text += "нет участников\n\n"
            continue
        for row in rows:
            user_link = f"https://t.me/user?id={row['user_id']}"
            text += f"#{row['number']} — {user_link}\n"
        text += "\n"
    await update.message.reply_text(text)

# -------------------- /check --------------------
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("/check 27")
        return
    number = int(context.args[0])
    cursor.execute("SELECT user_id, date, link FROM tickets WHERE number=%s", (number,))
    row = cursor.fetchone()
    if row:
        user_link = f"https://t.me/user?id={row['user_id']}"
        await update.message.reply_text(f"🎟 Номер: {number}\n👤 {user_link}\n📅 {row['date']}\n🔗 {row['link']}")
    else:
        await update.message.reply_text("Не найден")

# -------------------- /data --------------------
async def data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await update.message.reply_document(document=open("tickets.db", "rb"), filename="tickets.db")

# -------------------- /reset --------------------
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    keyboard = [[InlineKeyboardButton("✅ Да", callback_data="reset_yes"),
                 InlineKeyboardButton("❌ Нет", callback_data="reset_no")]]
    await update.message.reply_text("Сбросить розыгрыш?", reply_markup=InlineKeyboardMarkup(keyboard))

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

# -------------------- Ответы на сообщения магазина --------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.lower()
    chat_id = update.effective_chat.id
    shop = SHOPS.get(chat_id)
    if not shop:
        return
    if is_blacklisted_link(text):
        return
    if any(k in text for k in ADDRESS_KEYWORDS):
        await update.message.reply_text(shop["address"], reply_to_message_id=update.message.message_id)
    elif any(k in text for k in WORK_KEYWORDS):
        await update.message.reply_text(shop["work_time"], reply_to_message_id=update.message.message_id)
    elif any(k in text for k in MAX_KEYWORDS):
        await update.message.reply_text(shop["max_link"], reply_to_message_id=update.message.message_id)

# -------------------- Регистрация --------------------
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("id", get_id))
app.add_handler(CommandHandler("stat", stat))
app.add_handler(CommandHandler("today", today))
app.add_handler(CommandHandler("check", check))
app.add_handler(CommandHandler("data", data))
app.add_handler(CommandHandler("reset", reset))
app.add_handler(CallbackQueryHandler(reset_confirm))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_review))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# -------------------- Запуск --------------------
app.run_polling()