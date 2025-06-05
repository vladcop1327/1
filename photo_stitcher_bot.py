import os
import logging
from io import BytesIO
from PIL import Image
from telegram import Update, InputMediaPhoto, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = "8061285829:AAFMjY72I6W3yKDtbR5MaIT72F-R61wFcAM"
BASE_URL = "http://localhost:8000/static"

user_state = {}
user_photos = {}
user_settings = {}

WAITING_COUNT = "waiting_count"
WAITING_PHOTOS = "waiting_photos"
WAITING_DESCRIPTION = "waiting_description"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = WAITING_COUNT
    user_photos[user_id] = []
    user_settings[user_id] = {}

    keyboard = [[KeyboardButton("2 фото")], [KeyboardButton("3 фото")]]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("👋 Сколько фото хочешь сшить?", reply_markup=markup)

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
            return await update.message.reply_text("❗ Выбери: 2 фото или 3 фото.")
        user_state[user_id] = WAITING_PHOTOS
        await update.message.reply_text("📸 Отправь фото (по одному или все сразу).")

    elif state == WAITING_DESCRIPTION:
        description = update.message.text
        await update.message.reply_text("🌀 Обрабатываю...")
        await send_collage(update, context, description)
        user_state[user_id] = None
        user_photos[user_id] = []
        user_settings[user_id] = {}

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_state.get(user_id) != WAITING_PHOTOS:
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
    max_height = max(img.height for img in pil_images)
    resized = [img.resize((int(img.width * max_height / img.height), max_height)) for img in pil_images]
    total_width = sum(img.width for img in resized)

    collage = Image.new("RGB", (total_width, max_height))
    x_offset = 0
    for img in resized:
        collage.paste(img, (x_offset, 0))
        x_offset += img.width
    return collage

async def send_collage(update, context, description):
    user_id = update.effective_user.id
    images = user_photos.get(user_id, [])
    if not images:
        return await update.message.reply_text("❌ Фото не найдены.")

    result_image = stitch_images(images)
    os.makedirs("static", exist_ok=True)
    filename = f"collage_{user_id}.jpg"
    path = os.path.join("static", filename)
    result_image.save(path, format="JPEG", quality=90)

    url = f"{BASE_URL}/{filename}"
    with open(path, "rb") as photo:
        await update.message.reply_photo(
            photo=photo,
            caption=f"📝 {description}\n🔗 Ссылка на файл: {url}"
        )

async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    await app.run_polling()

if __name__ == "__main__":
    import asyncio, nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
