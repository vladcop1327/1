import logging
import os
from io import BytesIO
from PIL import Image
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from fpdf import FPDF
import requests


TOKEN = os.getenv("BOT_TOKEN")


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
        "👋 Привет! Я помогу тебе создать PDF из фотографий.\n\nСколько фото ты хочешь сшить?",
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
        await update.message.reply_text("🌀 Создаю PDF...")
        await send_pdf(update, context, description)
        user_state[user_id] = None
        user_photos[user_id] = []
        user_settings[user_id] = {}


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id)

    if state != WAITING_PHOTOS:
        return await update.message.reply_text("🔁 Напиши /start чтобы начать сначала")

    photo = await update.message.photo[-1].get_file()
    data = await photo.download_as_bytearray()
    user_photos[user_id].append(BytesIO(data))

    expected = user_settings[user_id].get("count")
    if len(user_photos[user_id]) >= expected:
        user_state[user_id] = WAITING_DESCRIPTION
        await update.message.reply_text("✍️ Напиши общее описание для PDF:")


def create_pdf_from_images(images, filename):
    pdf = FPDF()
    for idx, img in enumerate(images):
        img.seek(0)
        image_path = f"{filename}_{idx}.jpg"
        with open(image_path, 'wb') as f:
            f.write(img.read())

        pdf.add_page()
        pdf.image(image_path, x=10, y=10, w=190)
        os.remove(image_path)
    pdf.output(f"{filename}.pdf")


def upload_pdf_to_transfer_sh(filepath):
    with open(filepath, 'rb') as f:
        response = requests.put(f"https://transfer.sh/{os.path.basename(filepath)}", data=f)
    return response.text.strip()


async def send_pdf(update, context, description):
    user_id = update.effective_user.id
    images = user_photos[user_id]

    if not images:
        return await update.message.reply_text("❌ Фото не найдены.")

    filename = f"collage_{user_id}"
    create_pdf_from_images(images, filename)
    try:
        url = upload_pdf_to_transfer_sh(f"{filename}.pdf")
        await update.message.reply_text(
            f"✅ PDF готов!\n\n🔗 Ссылка на файл: {url}\n\n📝 Описание: {description}"
        )
    except Exception as e:
        logger.error(f"Ошибка при загрузке: {e}")
        await update.message.reply_text("❌ Ошибка при загрузке PDF.")
    finally:
        if os.path.exists(f"{filename}.pdf"):
            os.remove(f"{filename}.pdf")


async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    await app.run_polling()

if __name__ == '__main__':
    import asyncio
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())