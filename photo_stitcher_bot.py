import os
import logging
from io import BytesIO
from PIL import Image
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")
BASE_URL = os.getenv("BASE_URL")  # https://one-pb08.onrender.com

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

    await update.message.reply_text("👋 Привет! Сколько фото ты хочешь сшить?", reply_markup=markup)


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
            await update.message.reply_text("❗ Пожалуйста, выбери: 2 фото или 3 фото.")
            return
        user_state[user_id] = WAITING_PHOTOS
        await update.message.reply_text("📸 Отправь фотографии (по одной или все сразу).")

    elif state == WAITING_DESCRIPTION:
        description = update.message.text
        await update.message.reply_text("🌀 Обрабатываю изображения...")
        await send_collage(update, context, description)
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
        await update.message.reply_text("✍️ Напиши описание к коллажу:")


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


def upload_to_imgbb(image: Image.Image):
    buffered = BytesIO()
    image.save(buffered, format="JPEG")
    buffered.seek(0)
    response = requests.post(
        "https://api.imgbb.com/1/upload",
        data={"key": IMGBB_API_KEY},
        files={"image": buffered}
    )
    data = response.json()
    return data["data"]["url"]


async def send_collage(update: Update, context: ContextTypes.DEFAULT_TYPE, description: str):
    user_id = update.effective_user.id
    images = user_photos[user_id]
    if not images:
        return await update.message.reply_text("❌ Фото не найдены.")

    result_image = stitch_images(images)

    try:
        link = upload_to_imgbb(result_image)
        await update.message.reply_photo(
            photo=link,
            caption=f"📝 {description}\n\n🔗 Ссылка: {link}"
        )
    except Exception as e:
        logger.error(f"Ошибка при загрузке на imgbb: {e}")
        await update.message.reply_text("❌ Ошибка при загрузке изображения.")


async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    webhook_url = f"{BASE_URL}/webhook"
    await app.bot.set_webhook(webhook_url)
    await app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        webhook_url=webhook_url,
    )

if __name__ == "__main__":
    import asyncio
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
