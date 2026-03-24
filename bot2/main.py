from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, CommandHandler, filters
import re
from rapidfuzz import fuzz
import string

TOKEN ="8632066324:AAHTAri1Owiv_T7-OfebMF9vFsBhQxDOFmU"

SHOPS = {
    -1003450185997: {
        "address": "📍 Наш адрес: Майкоп, ул. Строителей 8Б (район железного рынка)",
        "work_time": "🕒 Мы работаем: 10:00–19:00 каждый день, кроме понедельника"
    },
    -1003777692701: {
        "address": "📍 Наш адрес: Майкоп, ул. Депутатская 16Б",
        "work_time": "🕒 Мы работаем: 10:00–19:00 каждый день, кроме понедельника"
    },
    -1003840431977: {  
        "address": "📍 Наш адрес: Лабинск, ул. Победы 161 (Торговый комплекс Кубань)",
        "work_time": "🕒 Мы работаем: 09:00–18:00 каждый день, кроме понедельника"
    }
}

MAX_TEXT = "📱 Мы есть в MAX: https://max.ru/join/IMHKjeOxfKJFcRQTQVrhlCGvLx-qOzAUiTpxCussSr0"

BLACKLIST = ["есть"]

ADDRESS_KEYWORDS = ["адрес", "где найти", "где приехать", "где вы", "где находитесь", "как найти"]
WORK_KEYWORDS = ["время работы", "работаете", "до скольки", "рабочий день", "график работы"]
MAX_KEYWORDS = ["max","макс","в максе","есть ли макс","есть ли вы в максе","ссылка на макс","есть ли max","есть ли вы в max","соцсеть макс"]

THRESHOLD = 85


def clean(text: str) -> str:
    return text.lower().translate(str.maketrans('', '', string.punctuation)).strip()


def is_relevant(text: str, keywords: list) -> bool:
    text = clean(text)


    if text in BLACKLIST:
        return False

    # игнор "сколько", если не про работу
    if "сколько" in text and "работ" not in text:
        return False

    for word in keywords:
        clean_word = clean(word)

        if re.search(r'\b' + re.escape(clean_word) + r'\b', text):
            return True

        if fuzz.partial_ratio(clean_word, text) >= THRESHOLD:
            return True

    return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text
    chat_id = update.effective_chat.id

    # получаем данные магазина
    shop = SHOPS.get(chat_id)

    # если чат не зарегистрирован — молчим
    if not shop:
        return

    if is_relevant(text, ADDRESS_KEYWORDS):
        await update.message.reply_text(
            shop["address"],
            reply_to_message_id=update.message.message_id
        )
        return

    if is_relevant(text, WORK_KEYWORDS):
        await update.message.reply_text(
            shop["work_time"],
            reply_to_message_id=update.message.message_id
        )
        return

    if is_relevant(text, MAX_KEYWORDS):
        await update.message.reply_text(
            MAX_TEXT,
            reply_to_message_id=update.message.message_id
        )
        return
    
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(str(update.effective_chat.id))
# Создание приложения и добавление обработчика
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("id", get_id))
app.add_handler(MessageHandler(filters.TEXT, handle_message))


# Запуск бота
app.run_polling()