import os
import string
from datetime import datetime
import asyncpg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
import random

TOKEN = os.environ.get("TOKENOTVET")
DATABASE_URL = os.environ.get("DATABASE_URL")  # PostgreSQL URL от Railway
ADMIN_IDS = [1014380197, 866973179]

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
        "address": "📍 Лабинск, ул. Победы 161",
        "work_time": "🕒 Мы работаем: 09:00–18:00 каждый день!",
        "max_link": "📱 Мы есть в MAX: https://max.ru/join/caMNU_JQa9Q1-UlwqS1r6G9AECURkQn0ARdLGtM25wI"
    }
}

BLACKLIST_LINKS = ["https://max.ru/join"]
REVIEW_HASHTAG = "#отзыв"
REVIEW_CHATS = {
    -1003450185997: "Майкоп Строителей",
    -1003777692701: "Майкоп Депутатская",
    -1003840431977: "Лабинск"
}

REPLY_MESSAGES = [
    "Ваш номерок принят, спасибо за покупку! 🎟",
    "Спасибо за отзыв! Ваш номер участника: #{number} ✅",
    "Отзыв получен, вот ваш номерок: #{number} ✨",
]

# ---------------- Вспомогательные ----------------
def clean(text: str) -> str:
    return text.lower().translate(str.maketrans('', '', string.punctuation)).strip()

def is_blacklisted_link(text: str) -> bool:
    return any(link in text for link in BLACKLIST_LINKS)

# ---------------- PostgreSQL ----------------
async def init_db():
    pool = await asyncpg.create_pool(DATABASE_URL, ssl="require")
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                user_id BIGINT,
                number INTEGER,
                date DATE,
                link TEXT
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS counters (
                chat_id BIGINT PRIMARY KEY,
                counter INTEGER
            );
        """)
    return pool

async def get_next_number(pool, chat_id):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT counter FROM counters WHERE chat_id=$1", chat_id)
        if row:
            number = row["counter"] + 1
            await conn.execute("UPDATE counters SET counter=$1 WHERE chat_id=$2", number, chat_id)
        else:
            number = 1
            await conn.execute("INSERT INTO counters(chat_id, counter) VALUES($1, $2)", chat_id, number)
        return number

async def save_ticket(pool, chat_id, user_id, number, link, date):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO tickets(chat_id, user_id, number, date, link) VALUES($1,$2,$3,$4,$5)",
            chat_id, user_id, number, date, link
        )

async def get_user_ticket(pool, chat_id, user_id, date):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT number, link FROM tickets WHERE chat_id=$1 AND user_id=$2 AND date=$3",
            chat_id, user_id, date
        )

async def reset_all(pool):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM tickets")
        await conn.execute("DELETE FROM counters")

# ---------------- Команды ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Чат активен, приятных покупок 🎉")

# ---------------- Обработка отзывов ----------------
async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    text = update.message.text.lower()
    today = datetime.utcnow().date()

    if chat_id not in REVIEW_CHATS or REVIEW_HASHTAG not in text or is_blacklisted_link(text):
        return

    pool = context.bot_data["db_pool"]
    already = await get_user_ticket(pool, chat_id, user_id, today)
    if already:
        return

    number = await get_next_number(pool, chat_id)
    msg_id = update.message.message_id
    chat_username = update.effective_chat.username
    if chat_username:
        link = f"https://t.me/{chat_username}/{msg_id}"
    else:
        chat_id_clean = str(chat_id).replace("-100", "")
        link = f"https://t.me/c/{chat_id_clean}/{msg_id}"

    await save_ticket(pool, chat_id, user_id, number, link, today)

    # Отвечаем в группе на сообщение
    reply_text = random.choice(REPLY_MESSAGES).replace("{number}", str(number))
    await update.message.reply_text(reply_text, reply_to_message_id=update.message.message_id)

# ---------------- Админ команды ----------------
async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    today_date = datetime.utcnow().date()
    text = "📅 Сегодняшние участники:\n\n"
    pool = context.bot_data["db_pool"]
    async with pool.acquire() as conn:
        for chat_id, name in REVIEW_CHATS.items():
            rows = await conn.fetch(
                "SELECT number, user_id FROM tickets WHERE chat_id=$1 AND date=$2 ORDER BY number",
                chat_id, today_date
            )
            text += f"{name}\n"
            if not rows:
                text += "нет участников\n\n"
                continue
            for r in rows:
                user_link = f"https://t.me/user?id={r['user_id']}"
                text += f"#{r['number']} — {user_link}\n"
            text += "\n"
    await update.message.reply_text(text)

async def stat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    today_date = datetime.utcnow().date()
    text = "📊 Статистика\n\n"
    pool = context.bot_data["db_pool"]
    async with pool.acquire() as conn:
        for chat_id, name in REVIEW_CHATS.items():
            today_count = await conn.fetchval(
                "SELECT COUNT(*) FROM tickets WHERE chat_id=$1 AND date=$2", chat_id, today_date
            )
            total_count = await conn.fetchval(
                "SELECT COUNT(*) FROM tickets WHERE chat_id=$1", chat_id
            )
            text += f"{name}\nСегодня: {today_count}\nВсего: {total_count}\n\n"
    await update.message.reply_text(text)

async def check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("/check 27")
        return
    number = int(context.args[0])
    pool = context.bot_data["db_pool"]
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT user_id, date, link FROM tickets WHERE number=$1", number)
    if row:
        user_link = f"https://t.me/user?id={row['user_id']}"
        await update.message.reply_text(
            f"🎟 Номер: {number}\n👤 User: {user_link}\n📅 {row['date']}\n🔗 {row['link']}"
        )
    else:
        await update.message.reply_text("Не найден")

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    keyboard = [[
        InlineKeyboardButton("✅ Да", callback_data="reset_yes"),
        InlineKeyboardButton("❌ Нет", callback_data="reset_no")
    ]]
    await update.message.reply_text("Сбросить розыгрыш?", reply_markup=InlineKeyboardMarkup(keyboard))

async def reset_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pool = context.bot_data["db_pool"]
    if query.data == "reset_yes":
        await reset_all(pool)
        await query.edit_message_text("Розыгрыш сброшен")
    else:
        await query.edit_message_text("Отмена")

# ---------------- Main ----------------
async def main():
    pool = await init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.bot_data["db_pool"] = pool

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today_cmd))
    app.add_handler(CommandHandler("stat", stat_cmd))
    app.add_handler(CommandHandler("check", check_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CallbackQueryHandler(reset_confirm))

    # Обработка сообщений
    app.add_handler(MessageHandler(filters.TEXT & (filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP), handle_review))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_review))  # для админов ЛС

    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())