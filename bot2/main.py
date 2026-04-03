import os
import string
from datetime import datetime
import asyncpg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

TOKEN = os.environ.get("TOKENOTVET")
DATABASE_URL = os.environ.get("DATABASE_URL")

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

# ---------------- Подключение к PostgreSQL ----------------
async def init_db(application):
    pool = await asyncpg.create_pool(DATABASE_URL)
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
    application.bot_data["db_pool"] = pool

# ---------------- Логика номеров ----------------
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

# ---------------- Команды ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Чат активен, приятных покупок 🎉")

# ---------------- Основной обработчик отзывов ----------------
async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    text = update.message.text.lower()
    today = datetime.utcnow().date()

    if chat_id not in REVIEW_CHATS:
        return
    if REVIEW_HASHTAG not in text or is_blacklisted_link(text):
        return

    pool = context.bot_data["db_pool"]
    async with pool.acquire() as conn:
        already = await conn.fetchrow(
            "SELECT 1 FROM tickets WHERE chat_id=$1 AND user_id=$2 AND date=$3",
            chat_id, user_id, today
        )
        if already:
            await update.message.reply_text("⚠️ Вы уже получили номерок сегодня!")
            return

        number = await get_next_number(pool, chat_id)

        msg_id = update.message.message_id
        chat_username = update.effective_chat.username
        if chat_username:
            link = f"https://t.me/{chat_username}/{msg_id}"
        else:
            chat_id_clean = str(chat_id).replace("-100", "")
            link = f"https://t.me/c/{chat_id_clean}/{msg_id}"

        await conn.execute(
            "INSERT INTO tickets(chat_id, user_id, number, date, link) VALUES($1,$2,$3,$4,$5)",
            chat_id, user_id, number, today, link
        )

    await update.message.reply_text(f"🎟 Ваш номерок участника: #{number}")

# ---------------- Админ команды ----------------
async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    today_date = datetime.utcnow().date()
    text = "📅 Сегодняшние участники:\n\n"
    pool = context.bot_data["db_pool"]
    async with pool.acquire() as conn:
        for cid, name in REVIEW_CHATS.items():
            rows = await conn.fetch(
                "SELECT number, user_id FROM tickets WHERE chat_id=$1 AND date=$2 ORDER BY number",
                cid, today_date
            )
            text += f"*{name}*\n"
            if not rows:
                text += "нет участников\n\n"
                continue
            for r in rows:
                user_link = f"[#{r['number']}](tg://user?id={r['user_id']})"
                text += f"{user_link}\n"
            text += "\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def stat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    today_date = datetime.utcnow().date()
    text = "📊 Статистика\n\n"
    pool = context.bot_data["db_pool"]
    async with pool.acquire() as conn:
        for cid, name in REVIEW_CHATS.items():
            today_count = await conn.fetchval(
                "SELECT COUNT(*) FROM tickets WHERE chat_id=$1 AND date=$2", cid, today_date
            )
            total_count = await conn.fetchval(
                "SELECT COUNT(*) FROM tickets WHERE chat_id=$1", cid
            )
            text += f"*{name}*\nСегодня: {today_count}\nВсего: {total_count}\n\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Использование: /check 27")
        return
    number = int(context.args[0])
    pool = context.bot_data["db_pool"]
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT user_id, date, link FROM tickets WHERE number=$1", number)
    if row:
        await update.message.reply_text(
            f"🎟 Номер: {number}\n"
            f"👤 User: tg://user?id={row['user_id']}\n"
            f"📅 {row['date']}\n"
            f"🔗 {row['link']}"
        )
    else:
        await update.message.reply_text("❌ Не найден")

# ---------------- Reset ----------------
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM tickets")
            await conn.execute("DELETE FROM counters")
        await query.edit_message_text("✅ Розыгрыш сброшен")
    else:
        await query.edit_message_text("❌ Отмена")

# ---------------- Main ----------------
def main():
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(init_db)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today_cmd))
    app.add_handler(CommandHandler("stat", stat_cmd))
    app.add_handler(CommandHandler("check", check_cmd))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(reset_confirm))
    app.add_handler(MessageHandler(
        filters.TEXT & (filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP),
        handle_review
    ))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()