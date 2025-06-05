import logging
import os
from io import BytesIO
from PIL import Image
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters


TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = os.getenv("https://one-pb08.onrender.com")  


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


user_state = {}
user_photos = {}
user_settings = {}


WAITING_COUNT = "waiting_count"
WAITING_PHOTOS = "waiting_photos"
WAITING_DESCRIPTION = "waiting_description"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = WAITING_COUNT
    user_photos[user_id] = []
    user_settings[user_id] = {}

    keyboard = [[KeyboardButton("2 фото")], [KeyboardButton("3 фото")]]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text(
        "👋 Привет! Сколько фото хочешь сшить?",
        reply_markup=markup
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id)
    text = update.message.text.lower()

    if state == WAITING_COUNT:
        if "2" in text:
            user_settings[user_id]["count"] = 2
        elif "3" in text:
            user_settings[user_id]["count"] = 3
        else:
            await update.message.reply_text("❗ Выбери: 2 фото или 3 фото.")
            return
        user_state[user_id] = WAITING_PHOTOS
        await update.message.reply_text("📸 Отправь фото (по одному или все сразу).")

    elif state == WAITING_DESCRIPTION:
        description = update.message.text
        await update.message.reply_text("🌀 Обрабатываю...")
        await send_collage_link(update, context, description)
        user_state[user_id] = None
        user_photos[user_id] = []
        user_settings[user_id] = {}


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id)

    if state != WAITING_PHOTOS:
        return await update.message.reply_text("🔁 Напиши /start чтобы начать заново.")

    photo = await update.message.photo[-1].get_file()
    data = await photo.download_as_bytearray()
    user_photos[user_id].append(BytesIO(data))

    expected = user_settings[user_id].get("count")
    if len(user_photos[user_id]) >= expected:
        user_state[user_id] = WAITING_DESCRIPTION
        await update.message.reply_text("✍️ Напиши описание для коллажа:")


def stitch_images(images):
    pil_images = [Image.open(img).convert("RGB") for img in images]
    max_h = max(i.height for i in pil_images)
    resized = [i.resize((int(i.width * max_h / i.height), max_h)) for i in pil_images]
    total_w = sum(i.width for i in resized)
    result = Image.new('RGB', (total_w, max_h))
    x = 0
    for i in resized:
        result.paste(i, (x, 0))
        x += i.width
    return result


async def send_collage_link(update, context, description):
    user_id = update.effective_user.id
    images = user_photos[user_id]
    if not images:
        return await update.message.reply_text("❌ Фото не найдены")

    result = stitch_images(images)
    filename = f"collage_{user_id}.jpg"
    output_path = os.path.join("static", filename)

   
    os.makedirs("static", exist_ok=True)
    result.save(output_path, format="JPEG", quality=85)

    link = f"{BASE_URL}/static/{filename}"
    await update.message.reply_photo(
        photo=link,
        caption=f"📝 {description}\n\n🔗 Ссылка: {link}"
    )


async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    await app.run_polling()

if __name__ == '__main__':
    import asyncio, nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
