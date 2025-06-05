import logging
from io import BytesIO
from PIL import Image
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegraph import upload_file
import asyncio
import nest_asyncio

nest_asyncio.apply()

TOKEN = '8061285829:AAFMjY72I6W3yKDtbR5MaIT72F-R61wFcAM'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


user_state = {}
user_photos = {}
user_descriptions = {}
user_settings = {}

WAITING_DIRECTION = "waiting_direction"
WAITING_COUNT = "waiting_count"
WAITING_PHOTOS = "waiting_photos"
WAITING_DESCRIPTION = "waiting_description"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = WAITING_DIRECTION
    user_settings[user_id] = {}
    user_photos[user_id] = []
    user_descriptions[user_id] = []

    keyboard = [[KeyboardButton("По горизонтали")], [KeyboardButton("По вертикали")]]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text("🛍️ Выбери направление сшивания:", reply_markup=markup)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().lower()

    state = user_state.get(user_id)

    if state == WAITING_DIRECTION:
        if "горизонт" in text:
            user_settings[user_id]["direction"] = "horizontal"
        elif "вертикал" in text:
            user_settings[user_id]["direction"] = "vertical"
        else:
            await update.message.reply_text("⚠️ Выбери: По горизонтали или По вертикали.")
            return

        user_state[user_id] = WAITING_COUNT
        keyboard = [[KeyboardButton("2 фото")], [KeyboardButton("3 фото")]]
        markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("🔢 Сколько фото хочешь сшить?", reply_markup=markup)

    elif state == WAITING_COUNT:
        if "2" in text:
            user_settings[user_id]["count"] = 2
        elif "3" in text:
            user_settings[user_id]["count"] = 3
        else:
            await update.message.reply_text("⚠️ Выбери: 2 фото или 3 фото.")
            return

        user_state[user_id] = WAITING_PHOTOS
        await update.message.reply_text("📷 Отлично! Отправь фото #1:", reply_markup=ReplyKeyboardRemove())

    elif state == WAITING_DESCRIPTION:
        user_descriptions[user_id].append(update.message.text)

        if len(user_descriptions[user_id]) < user_settings[user_id]["count"]:
            await update.message.reply_text(f"🔍 Введи описание для фото #{len(user_descriptions[user_id]) + 1}:")
        else:
            await update.message.reply_text("🔧 Обрабатываю фото, подожди...")
            await send_stitched_image(update, context, user_id)
            user_state[user_id] = None
            user_photos[user_id] = []
            user_descriptions[user_id] = []


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id)

    if state != WAITING_PHOTOS:
        await update.message.reply_text("Сначала используй /start, чтобы задать параметры.")
        return

    photo_file = await update.message.photo[-1].get_file()
    byte_data = await photo_file.download_as_bytearray()
    user_photos[user_id].append(BytesIO(byte_data))

    if len(user_photos[user_id]) < user_settings[user_id]["count"]:
        await update.message.reply_text(f"✅ Принято! Отправь фото #{len(user_photos[user_id]) + 1}:")
    elif len(user_photos[user_id]) == user_settings[user_id]["count"]:
        user_state[user_id] = WAITING_DESCRIPTION
        await update.message.reply_text(f"🔍 Введи описание для фото #1:")


async def send_stitched_image(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id=None):
    if user_id is None:
        user_id = update.effective_user.id

    images = user_photos[user_id]
    direction = user_settings[user_id].get("direction", "horizontal")
    descriptions = user_descriptions[user_id]

    stitched = stitch_images(images, direction)

    with open(f"collage_{user_id}.jpg", "wb") as f:
        f.write(stitched.getbuffer())

    try:
        response = upload_file(f"collage_{user_id}.jpg")
        url = f"https://telegra.ph{response[0]}"
        desc_text = "\n\n".join([f"Фото {i+1}: {desc}" for i, desc in enumerate(descriptions)])
        await update.message.reply_text(f"🔗 Готово! Вот ссылка на коллаж:\n{url}\n\n📄 Описания:\n{desc_text}")
    except Exception as e:
        logger.error(f"Ошибка загрузки в Telegraph: {e}")
        await update.message.reply_text("Произошла ошибка при загрузке на Telegraph.")


def stitch_images(images, direction='horizontal'):
    pil_images = [Image.open(img).convert("RGB") for img in images]

    if direction == 'horizontal':
        max_height = max(img.height for img in pil_images)
        resized = [img.resize((int(img.width * max_height / img.height), max_height)) for img in pil_images]
        total_width = sum(img.width for img in resized)
        result = Image.new('RGB', (total_width, max_height))
        x = 0
        for img in resized:
            result.paste(img, (x, 0))
            x += img.width
    else:
        max_width = max(img.width for img in pil_images)
        resized = [img.resize((max_width, int(img.height * max_width / img.width))) for img in pil_images]
        total_height = sum(img.height for img in resized)
        result = Image.new('RGB', (max_width, total_height))
        y = 0
        for img in resized:
            result.paste(img, (0, y))
            y += img.height

    output = BytesIO()
    result.save(output, format='JPEG')
    output.seek(0)
    return output


async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("✅ Бот запущен...")
    await app.run_polling()


if __name__ == '__main__':
    asyncio.run(main())
