import logging
from io import BytesIO
from PIL import Image
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import nest_asyncio
import asyncio

nest_asyncio.apply()


TOKEN = '8061285829:AAFMjY72I6W3yKDtbR5MaIT72F-R61wFcAM' 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния
WAITING_DIRECTION = "waiting_direction"
WAITING_COUNT = "waiting_count"
WAITING_PHOTOS = "waiting_photos"

# Словари для хранения данных пользователей
user_state = {}        # user_id -> текущее состояние
user_photos = {}       # user_id -> список фото
user_settings = {}     # user_id -> {direction, count}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = WAITING_DIRECTION
    user_settings[user_id] = {}

    keyboard = [[KeyboardButton("По горизонтали")], [KeyboardButton("По вертикали")]]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text("📐 Выбери направление сшивания:", reply_markup=markup)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().lower()

    # Выбор направления
    if user_state.get(user_id) == WAITING_DIRECTION:
        if "горизонт" in text:
            user_settings[user_id]["direction"] = "horizontal"
        elif "вертикал" in text:
            user_settings[user_id]["direction"] = "vertical"
        else:
            await update.message.reply_text("❗ Пожалуйста, выбери: По горизонтали или По вертикали.")
            return

        user_state[user_id] = WAITING_COUNT
        keyboard = [[KeyboardButton("2 фото")], [KeyboardButton("3 фото")]]
        markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("📸 Сколько фото хочешь сшить?", reply_markup=markup)
        return

    # Выбор количества фото
    if user_state.get(user_id) == WAITING_COUNT:
        if "2" in text:
            user_settings[user_id]["count"] = 2
        elif "3" in text:
            user_settings[user_id]["count"] = 3
        else:
            await update.message.reply_text("❗ Пожалуйста, выбери: 2 фото или 3 фото.")
            return

        user_state[user_id] = WAITING_PHOTOS
        user_photos[user_id] = []

        await update.message.reply_text(
            f"✅ Отлично! Отправь {user_settings[user_id]['count']} фото для сшивания.",
            reply_markup=ReplyKeyboardRemove()
        )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_state.get(user_id) != WAITING_PHOTOS:
        await update.message.reply_text("🔄 Сначала используй команду /start, чтобы выбрать настройки.")
        return

    # Получаем фото и добавляем во временное хранилище
    photo_file = await update.message.photo[-1].get_file()
    byte_data = await photo_file.download_as_bytearray()
    photo = BytesIO(byte_data)

    user_photos[user_id].append(photo)
    count_needed = user_settings[user_id]["count"]
    count_now = len(user_photos[user_id])

    if count_now < count_needed:
        await update.message.reply_text(f"📥 Принято! Жду ещё {count_needed - count_now} фото...")
    elif count_now == count_needed:
        await update.message.reply_text("🔧 Обрабатываю фото, подожди немного...")
        await send_stitched_image(update, context, user_id)
        user_photos[user_id] = []
        user_state[user_id] = None
    else:
        await update.message.reply_text("⚠️ Слишком много фото. Начни заново с /start.")
        user_photos[user_id] = []
        user_state[user_id] = None


async def send_stitched_image(update, context, user_id):
    images = user_photos[user_id]
    direction = user_settings[user_id].get("direction", "horizontal")

    try:
        stitched = stitch_images(images, direction)
        await update.message.reply_photo(photo=stitched)
    except Exception as e:
        logger.error(f"❌ Ошибка при сшивании: {e}")
        await update.message.reply_text("Произошла ошибка при сшивании изображений.")


def stitch_images(images, direction='horizontal'):
    pil_images = [Image.open(img).convert("RGB") for img in images]

    # Масштабируем все изображения к одной высоте или ширине
    if direction == 'horizontal':
        max_height = max(img.height for img in pil_images)
        resized = [img.resize((int(img.width * max_height / img.height), max_height)) for img in pil_images]
    else:
        max_width = max(img.width for img in pil_images)
        resized = [img.resize((max_width, int(img.height * max_width / img.width))) for img in pil_images]

    # Объединяем изображения
    widths, heights = zip(*(img.size for img in resized))
    if direction == 'horizontal':
        total_width = sum(widths)
        result = Image.new('RGB', (total_width, max(heights)))
        x_offset = 0
        for img in resized:
            result.paste(img, (x_offset, 0))
            x_offset += img.width
    else:
        total_height = sum(heights)
        result = Image.new('RGB', (max(widths), total_height))
        y_offset = 0
        for img in resized:
            result.paste(img, (0, y_offset))
            y_offset += img.height

    # Возвращаем результат как байты
    output = BytesIO()
    result.save(output, format='JPEG')
    output.seek(0)
    return output


async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("🤖 Бот запущен...")
    await app.run_polling()


if __name__ == '__main__':
    asyncio.run(main())
