import logging
from io import BytesIO
from PIL import Image
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import os

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
        "👋 Привет! Сколько фото хочешь сшить?", reply_markup=markup
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
        await update.message.reply_text("🌀 Создаю PDF и изображение...")
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
        await update.message.reply_text("✍️ Напиши описание к коллажу:")

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

async def send_pdf(update, context, description):
    user_id = update.effective_user.id
    images = user_photos[user_id]
    if not images:
        return await update.message.reply_text("❌ Фото не найдены")

    stitched_image = stitch_images(images)

    # Сохраняем как PDF
    pdf_path = f"collage_{user_id}.pdf"
    stitched_image.save(pdf_path, "PDF", resolution=100.0)

    # Сохраняем как JPG для предпросмотра
    jpg_io = BytesIO()
    stitched_image.save(jpg_io, format='JPEG', quality=90)
    jpg_io.seek(0)

    try:
        # Отправляем изображение
        await update.message.reply_photo(
            photo=jpg_io,
            caption=f"📝 Описание: {description}"
        )

        # Отправляем PDF
        with open(pdf_path, "rb") as f:
            await update.message.reply_document(
                document=InputFile(f, filename="collage.pdf"),
                caption="📄 PDF-файл с коллажем"
            )
    except Exception as e:
        logger.error(f"Ошибка при отправке: {e}")
        await update.message.reply_text("❌ Ошибка при отправке файлов.")
    finally:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    await app.run_polling()

if __name__ == '__main__':
    import nest_asyncio
    import asyncio

    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
