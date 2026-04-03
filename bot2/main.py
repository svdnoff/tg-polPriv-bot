import os
import re
import string
import asyncio
import random
from datetime import datetime

import asyncpg
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, MessageHandler, ContextTypes,
    CommandHandler, CallbackQueryHandler, filters
)
from rapidfuzz import fuzz
from auto_reply import handle_auto_reply  # твоя старая функция автоответа

# ---------------- Конфигурация ----------------
TOKEN = os.environ.get("TOKENOTVET")
SUPABASE_URL = os.environ.get("SUPABASE_URL")  # postgres://user:pass@host:5432/postgres
ADMIN_IDS = [1014380197, 866973179]

# ---------------- Магазины ----------------
SHOPS = {
    -1003450185997: {"address": "📍 Майкоп, ул. Строителей 8Б", "work_time": "🕒 10:00–19:00", "max_link": "https://max.ru/join/IMHKjeOxfKJFcRQTQVrhlCGvLx-qOzAUiTpxCussSr0"},
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

REPLY_MESSAGES = [
    "Ваш номерок принят, спасибо за покупку! 🎟",
    "Спасибо за отзыв! Ваш номер участника: #{number} ✅",
    "Отзыв получен, вот ваш номерок: #{number} ✨",
]

ADDRESS_KEYWORDS = ["адрес", "где найти", "где приехать", "где вы", "где находитесь", "как найти"]
WORK_KEYWORDS = ["время работы", "работаете", "до скольки", "рабочий день", "график работы"]
MAX_KEYWORDS = ["max","макс","в максе","есть ли макс","есть ли вы в максе","ссылка на макс","есть ли max","есть ли вы в max","соцсеть макс"]
THRESHOLD = 85

db_pool = None  # глобальный пул соединений

# ---------------- Вспомогательные ----------------
def clean(text: str) -> str:
    return text.lower().translate(str.maketrans('', '', string.punctuation)).strip()

def is_blacklisted_link(text: str) -> bool:
    return any(link in text for link in BLACKLIST_LINKS)

# ---------------- Работа с базой ----------------
async def create_pool():
    global db_pool
    db_pool = await asyncpg.create_pool(SUPABASE_URL)
    # создаем таблицы, если их нет
    async with db_pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            number INT NOT NULL,
            date DATE NOT NULL,
            link TEXT NOT NULL
        )
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS counters (
            chat_id BIGINT PRIMARY KEY,
            counter INT NOT NULL
        )
        """)

async def get_next_number(chat_id: int) -> int:
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT counter FROM counters WHERE chat_id=$1", chat_id)
            if row:
                number = row['counter'] + 1
                await conn.execute("UPDATE counters SET counter=$1 WHERE chat_id=$2", number, chat_id)
            else:
                number = 1
                await conn.execute("INSERT INTO counters (chat_id, counter) VALUES ($1, $2)", chat_id, number)
    return number

async def save_ticket(chat_id: int, user_id: int, number: int, link: str, date: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO tickets (chat_id, user_id, number, date, link) VALUES ($1, $2, $3, $4, $5)",
            chat_id, user_id, number, date, link
        )

async def reset_counter(chat_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE counters SET counter=0 WHERE chat_id=$1", chat_id)
        await conn.execute("DELETE FROM tickets WHERE chat_id=$1", chat_id)

async def get_user_ticket(chat_id: int, user_id: int, date: str):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT number, link FROM tickets WHERE chat_id=$1 AND user_id=$2 AND date=$3", chat_id, user_id, date)

# ---------------- Команды ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Чат активен, приятных покупок 🎉")

async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    text = "📊 Статистика\n\n"
    async with db_pool.acquire() as conn:
        for chat_id, name in REVIEW_CHATS.items():
            today_count = await conn.fetchval("SELECT COUNT(*) FROM tickets WHERE chat_id=$1 AND date=$2", chat_id, today_str)
            total_count = await conn.fetchval("SELECT COUNT(*) FROM tickets WHERE chat_id=$1", chat_id)
            text += f"{name}\nСегодня: {today_count}\nВсего: {total_count}\n\n"
    await update.message.reply_text(text)

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    text = "📅 Сегодняшние участники:\n\n"
    async with db_pool.acquire() as conn:
        for chat_id, name in REVIEW_CHATS.items():
            rows = await conn.fetch("SELECT number, user_id FROM tickets WHERE chat_id=$1 AND date=$2 ORDER BY number", chat_id, today_str)
            text += f"{name}\n"
            if not rows:
                text += "нет участников\n\n"
                continue
            for row in rows:
                user_link = f"https://t.me/user?id={row['user_id']}"
                text += f"#{row['number']} — {user_link}\n"
            text += "\n"
    await update.message.reply_text(text)

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Ваш ID: {update.effective_user.id}")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    keyboard = [[("Подтвердить сброс", "reset_confirm")]]
    await update.message.reply_text("Вы уверены, что хотите сбросить все счетчики?", reply_markup=None)

async def reset_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
    else:
        chat_id = update.effective_chat.id
    await reset_counter(chat_id)
    await update.callback_query.message.reply_text("Счетчики и данные участников сброшены.")

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    user_ticket = await get_user_ticket(update.effective_chat.id, update.effective_user.id, today_str)
    if user_ticket:
        await update.message.reply_text(f"Ваш номер участника сегодня: #{user_ticket['number']}\nСсылка на сообщение: {user_ticket['link']}")
    else:
        await update.message.reply_text("Вы еще не оставляли отзыв сегодня.")

# ---------------- Обработка отзывов ----------------
async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    text = update.message.text.lower()
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    if chat_id not in REVIEW_CHATS or REVIEW_HASHTAG not in text or is_blacklisted_link(text):
        return

    # Проверка, писал ли уже сегодня
    user_ticket = await get_user_ticket(chat_id, user_id, today_str)
    if user_ticket:
        return  # уже есть номерок

    number = await get_next_number(chat_id)
    link = f"https://t.me/c/{str(chat_id).replace('-100','')}/{update.message.message_id}"
    await save_ticket(chat_id, user_id, number, link, today_str)

    reply_text = random.choice(REPLY_MESSAGES).replace("{number}", str(number))
    await update.message.reply_text(reply_text, reply_to_message_id=update.message.message_id)

# ---------------- Ответы на вопросы ----------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text
    chat_id = update.effective_chat.id
    shop = SHOPS.get(chat_id)
    if not shop or is_blacklisted_link(text):
        return
    def is_relevant(text, keywords):
        t = clean(text)
        for w in keywords:
            w_clean = clean(w)
            if re.search(r'\b'+re.escape(w_clean)+r'\b', t) or fuzz.partial_ratio(w_clean, t) >= THRESHOLD:
                return True
        return False
    if is_relevant(text, ADDRESS_KEYWORDS):
        await update.message.reply_text(shop["address"], reply_to_message_id=update.message.message_id)
        return
    if is_relevant(text, WORK_KEYWORDS):
        await update.message.reply_text(shop["work_time"], reply_to_message_id=update.message.message_id)
        return
    if is_relevant(text, MAX_KEYWORDS):
        await update.message.reply_text(shop["max_link"], reply_to_message_id=update.message.message_id)
        return

# ---------------- Запуск бота ----------------
async def main():
    await create_pool()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stat", stat))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("get_id", get_id))
    app.add_handler(CallbackQueryHandler(reset_confirm))

    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_review), group=0)
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_auto_reply), group=1)
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_message), group=2)

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())