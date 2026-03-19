from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from rapidfuzz import fuzz
import string

TOKEN = "8696298548:AAHC6-yyC9rlgz7W7VhiYjskxnoe4HbK-24"

# 📦 ПРАЙСЫ
PRICES = {
    "iphone": {
        "13": "📱 iPhone 13\n128GB — 45 000₽\n256GB — 50 000₽",
        "13 pro": "📱 iPhone 13 Pro\n128GB — 60 000₽\n256GB — 65 000₽",

        "14": "📱 iPhone 14\n128GB — 55 000₽\n256GB — 60 000₽",
        "14 pro": "📱 iPhone 14 Pro\n128GB — 75 000₽\n256GB — 85 000₽",

        "15": "📱 iPhone 15\n128GB — 70 000₽\n256GB — 80 000₽",
        "15 pro": "📱 iPhone 15 Pro\n128GB — 95 000₽\n256GB — 105 000₽",

        "16": "📱 iPhone 16\n128GB — 80 000₽\n256GB — 90 000₽",
        "16 pro": "📱 iPhone 16 Pro\n128GB — 105 000₽\n256GB — 115 000₽",

        "17": "📱 iPhone 17\n128GB — 90 000₽\n256GB — 100 000₽",
        "17 pro": "📱 iPhone 17 Pro\n128GB — 115 000₽\n256GB — 125 000₽",
    },
    "samsung": {
        "s23": "📱 Samsung Galaxy S23\n128GB — 60 000₽\n256GB — 65 000₽",
        "s24": "📱 Samsung Galaxy S24\n128GB — 70 000₽\n256GB — 75 000₽",
        "a54": "📱 Samsung Galaxy A54\n128GB — 35 000₽"
    }
}

# 🧠 СИНОНИМЫ
BRANDS = {
    "iphone": ["iphone", "айфон", "эпл", "apple"],
    "samsung": ["samsung", "самсунг", "самс"]
}

THRESHOLD = 85


# 🧹 ОЧИСТКА ТЕКСТА
def clean(text: str) -> str:
    return text.lower().translate(str.maketrans('', '', string.punctuation)).strip()


# 🔍 ПОИСК БРЕНДА
def detect_brand(text: str):
    text = clean(text)

    for brand, variants in BRANDS.items():
        for word in variants:
            if fuzz.partial_ratio(word, text) >= THRESHOLD:
                return brand

    return None


# 🔍 ПОИСК МОДЕЛИ
def detect_model(text: str, brand: str):
    text = clean(text)
    models = PRICES.get(brand, {})

    for model in models.keys():
        if fuzz.partial_ratio(model, text) >= THRESHOLD:
            return model

    return None


# 🤖 ОСНОВНОЙ ХЕНДЛЕР
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text

    brand = detect_brand(text)

    # если не нашли бренд — молчим
    if not brand:
        return

    model = detect_model(text, brand)

    # ✅ есть модель → отправляем прайс
    if model:
        await update.message.reply_text(
            PRICES[brand][model],
            reply_to_message_id=update.message.message_id
        )
        return

    # ⚠️ только бренд → просим уточнить
    await update.message.reply_text(
        f"Уточни модель {brand.upper()} 📱\n\nНапример:\n13 / 13 Pro / 14 / 15 Pro / S23",
        reply_to_message_id=update.message.message_id
    )


# 🚀 ЗАПУСК
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT, handle_message))

app.run_polling()