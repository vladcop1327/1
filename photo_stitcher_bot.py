import logging
from io import BytesIO
from PIL import Image
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegraph import upload_file
import asyncio
import nest_asyncio
import os

nest_asyncio.apply()

TOKEN = '8061285829:AAFMjY72I6W3yKDtbR5MaIT72F-R61wFcAM'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}
user_photos = {}
user_settings = {}

WAITING_DIRECTION = "waiting_direction"
WAITING_COUNT = "waiting_count"
WAITING_PHOTOS = "waiting_photos"
WAITING_DESCRIPTION = "waiting_description"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = WAITING_DIRECTION
    user_photos[user_id] = []
    user_settings[user_id] = {}

    keyboard = [
        [KeyboardButton("🧱 Горизонтально")],
        [KeyboardButton("📏 Вертикально")]
    ]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text(
        "👋 Привет! Я помогу тебе сшить 2 или 3 фото в один коллаж.\n\n"
        "Сначала выбери направление сшивки:",
        reply_markup=markup
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.lower()
    state = user_state.get(user_id)

    if state == WAITING_DIRECTION:
        if "гориз" in text:
            user_settings[user_id]["direction"] = "horizontal"
        elif "вертик" in text:
            user_settings[user_id]["direction"] = "vertical"
        else:
            await update.message.reply_text("❗ Выберите: Горизонтально или Вертикально.")
            return
        user_state[user_id] = WAITING_COUNT
        markup = ReplyKeyboardMarkup([[KeyboardButton("2 фото")], [KeyboardButton("3 фото")]],
                                     one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("📸 Сколько фото сшить?", reply_markup=markup)

    elif state == WAITING_COUNT:
        if "2" in text:
            user_settings[user_id]["count"] = 2
        elif "3" in text:
            user_settings[user_id]["count"] = 3
        else:
            await update.message.reply_text("❗ Выберите: 2 фото или 3 фото.")
            return
        user_state[user_id] = WAITING_PHOTOS
        await update.message.reply_text("📥 Отправьте фото #1:", reply_markup=ReplyKeyboardRemove())

    elif state == WAITING_DESCRIPTION:
        description = update.message.text
        await update.message.reply_text("⏳ Создаю коллаж, подождите...")
        await send_collage(update, context, description)
        user_state[user_id] = None
        user_photos[user_id] = []
        user_settings[user_id] = {}


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id)

    if state != WAITING_PHOTOS:
        await update.message.reply_text("❗ Сначала введите команду /start")
        return

    photo = await update.message.photo[-1].get_file()
    data = await photo.download_as_bytearray()
    user_photos[user_id].append(BytesIO(data))

    current = len(user_photos[user_id])
    total = user_settings[user_id]["count"]

    if current < total:
        await update.message.reply_text(f"✅ Фото {current} получено. Отправьте фото #{current + 1}:")
    else:
        user_state[user_id] = WAITING_DESCRIPTION
        await update.message.reply_text("📝 Введите общее описание для коллажа:")


async def send_collage(update, context, description):
    user_id = update.effective_user.id
    images = user_photos[user_id]
    direction = user_settings[user_id]["direction"]

    stitched = stitch_images(images, direction)

    filename = f"collage_{user_id}.jpg"
    with open(filename, "wb") as f:
        f.write(stitched.getbuffer())

    try:
        if not os.path.exists(filename):
            await update.message.reply_text("❌ Не удалось создать файл коллажа.")
            return

        response = upload_file(filename)
        url = f"https://telegra.ph{response[0]}"
        await update.message.reply_text(f"✅ Готово!\n🔗 Ссылка: {url}\n\n📝 Описание: {description}")
    except Exception as e:
        logger.error(f"Telegraph error: {e}")
        await update.message.reply_text("❌ Ошибка при загрузке в Telegraph. Убедитесь, что размер файла < 5MB.")


# Склейка

def stitch_images(images, direction):
    imgs = [Image.open(img).convert("RGB") for img in images]

    if direction == 'horizontal':
        max_h = max(i.height for i in imgs)
        imgs = [i.resize((int(i.width * max_h / i.height), max_h)) for i in imgs]
        total_w = sum(i.width for i in imgs)
        result = Image.new('RGB', (total_w, max_h))
        x = 0
        for i in imgs:
            result.paste(i, (x, 0))
            x += i.width
    else:
        max_w = max(i.width for i in imgs)
        imgs = [i.resize((max_w, int(i.height * max_w / i.width))) for i in imgs]
        total_h = sum(i.height for i in imgs)
        result = Image.new('RGB', (max_w, total_h))
        y = 0
        for i in imgs:
            result.paste(i, (0, y))
            y += i.height

    output = BytesIO()
    result.save(output, format='JPEG', quality=85)
    output.seek(0)
    return output


async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("✅ Бот запущен")
    await app.run_polling()


if __name__ == '__main__':
    asyncio.run(main())
