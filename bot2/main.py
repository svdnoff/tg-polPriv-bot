from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, CommandHandler, CallbackQueryHandler, filters
import json, os, string, re
from rapidfuzz import fuzz
from datetime import datetime

TOKEN = os.environ.get("TOKEN")

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
        "address": "📍 Наш адрес: Лабинск, ул. Победы 161 (Торговый комплекс Кубань)",
        "work_time": "🕒 Мы работаем: 09:00–18:00 каждый день!",
        "max_link": "📱 Мы есть в MAX: https://max.ru/join/caMNU_JQa9Q1-UlwqS1r6G9AECURkQn0ARdLGtM25wI"
    }
}

BLACKLIST = ["есть"]
BLACKLIST_LINKS = ["https://max.ru/join"]
ADDRESS_KEYWORDS = ["адрес", "где найти", "где приехать", "где вы", "где находитесь", "как найти"]
WORK_KEYWORDS = ["время работы", "работаете", "до скольки", "рабочий день", "график работы"]
MAX_KEYWORDS = ["max","макс","в максе","есть ли макс","есть ли вы в максе","ссылка на макс","есть ли max","есть ли вы в max","соцсеть макс"]
THRESHOLD = 85

REVIEW_HASHTAG = "#отзыв"
REVIEW_CHATS = {
    -1003450185997: "Майкоп Строителей",
    -1003777692701: "Майкоп Депутатская",
    -1003840431977: "Лабинск"
}

ADMIN_IDS = [1014380197, 866973179]
DATA_FILE = "tickets.json"

# -------------------- Глобальный словарь --------------------
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        TICKETS = json.load(f)
else:
    TICKETS = {}
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(TICKETS, f, ensure_ascii=False, indent=2)

# -------------------- Вспомогательные функции --------------------
def clean(text: str) -> str:
    return text.lower().translate(str.maketrans('', '', string.punctuation)).strip()

def is_blacklisted_link(text: str) -> bool:
    return any(link_fragment in text for link_fragment in BLACKLIST_LINKS)

def is_relevant(text: str, keywords: list) -> bool:
    text = clean(text)
    if text in BLACKLIST:
        return False
    if "сколько" in text and "работ" not in text:
        return False
    for word in keywords:
        clean_word = clean(word)
        if re.search(r'\b' + re.escape(clean_word) + r'\b', text):
            return True
        if fuzz.partial_ratio(clean_word, text) >= THRESHOLD:
            return True
    return False

# -------------------- Команды --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Чат активен, приятных покупок! 🎉")

# -------------------- Розыгрыш (#отзыв) --------------------
async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.lower()
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = str(user.id)
    today = datetime.utcnow().strftime("%Y-%m-%d")

    if chat_id not in REVIEW_CHATS or REVIEW_HASHTAG not in text:
        return
    if is_blacklisted_link(text):
        return

    global TICKETS
    chat_id_str = str(chat_id)
    if chat_id_str not in TICKETS:
        TICKETS[chat_id_str] = {"counter": 0, "users": {}, "history": []}

    chat_data = TICKETS[chat_id_str]

    if user_id in chat_data["users"] and chat_data["users"][user_id] == today:
        return  # уже выдавали сегодня

    chat_data["counter"] += 1
    number = chat_data["counter"]
    chat_data["users"][user_id] = today

    message_id = update.message.message_id
    chat_username = update.effective_chat.username
    if chat_username:
        link = f"https://t.me/{chat_username}/{message_id}"
    else:
        chat_id_clean = str(chat_id).replace("-100", "")
        link = f"https://t.me/c/{chat_id_clean}/{message_id}"

    chat_data["history"].append({
        "user": user_id,
        "number": number,
        "date": today,
        "link": link
    })

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(TICKETS, f, ensure_ascii=False, indent=2)

    try:
        await context.bot.send_message(chat_id=user.id, text=f"🎟 Ваш номер участника: #{number}")
    except:
        pass

# -------------------- Статистика --------------------
async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    global TICKETS
    today = datetime.utcnow().strftime("%Y-%m-%d")
    text = "📊 Статистика\n\n"
    for chat_id, name in REVIEW_CHATS.items():
        chat = TICKETS.get(str(chat_id), {"history":[]})
        today_count = sum(1 for x in chat.get("history", []) if x["date"] == today)
        total = len(chat.get("history", []))
        text += f"{name}\nСегодня: {today_count}\nВсего: {total}\n\n"
    await update.message.reply_text(text)

# -------------------- Проверка номера --------------------
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("/check 27")
        return
    number = int(context.args[0])
    global TICKETS
    for chat_id, chat in TICKETS.items():
        for entry in chat.get("history", []):
            if entry["number"] == number:
                await update.message.reply_text(
                    f"🎟 Номер: {number}\n"
                    f"👤 User ID: {entry['user']}\n"
                    f"📅 {entry['date']}\n"
                    f"🔗 {entry['link']}"
                )
                return
    await update.message.reply_text("Не найден")

# -------------------- Сброс розыгрыша --------------------
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    keyboard = [
        [InlineKeyboardButton("✅ Да", callback_data="reset_yes"),
         InlineKeyboardButton("❌ Нет", callback_data="reset_no")]
    ]
    await update.message.reply_text("Вы уверены что хотите сбросить розыгрыш?", reply_markup=InlineKeyboardMarkup(keyboard))

async def reset_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    global TICKETS
    if query.data == "reset_yes":
        TICKETS = {}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(TICKETS, f, ensure_ascii=False, indent=2)
        await query.edit_message_text("Розыгрыш сброшен")
    else:
        await query.edit_message_text("Отмена")

# -------------------- Ответы на сообщения магазина --------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text
    chat_id = update.effective_chat.id
    if is_blacklisted_link(text):
        return
    shop = SHOPS.get(chat_id)
    if not shop:
        return
    if is_relevant(text, ADDRESS_KEYWORDS):
        await update.message.reply_text(shop["address"], reply_to_message_id=update.message.message_id)
        return
    if is_relevant(text, WORK_KEYWORDS):
        await update.message.reply_text(shop["work_time"], reply_to_message_id=update.message.message_id)
        return
    if is_relevant(text, MAX_KEYWORDS):
        await update.message.reply_text(shop["max_link"], reply_to_message_id=update.message.message_id)
        return

# -------------------- Прочее --------------------
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(str(update.effective_chat.id))

# -------------------- Регистрация обработчиков --------------------
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("id", get_id))
app.add_handler(CommandHandler("stat", stat))
app.add_handler(CommandHandler("check", check))
app.add_handler(CommandHandler("reset", reset))
app.add_handler(CallbackQueryHandler(reset_confirm))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_review))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# -------------------- Запуск --------------------
app.run_polling()