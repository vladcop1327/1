import logging
from io import BytesIO
from PIL import Image
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegraph import Telegraph, upload_file
import asyncio
import nest_asyncio

nest_asyncio.apply()

TOKEN = '8061285829:AAFMjY72I6W3yKDtbR5MaIT72F-R61wFcAM'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

telegraph = Telegraph()
telegraph.create_account(short_name="photo_bot")

user_state = {}
user_photos = {}
user_descriptions = {}
user_settings = {}

WAITING_DIRECTION = "waiting_direction"
WAITING_COUNT = "waiting_count"
WAITING_PHOTOS = "waiting_photos"
WAITING_DESCRIPTION = "waiting_description"


def main_menu():
    keyboard = [[KeyboardButton("ГОРИЗОНТАЛЬНО")], [KeyboardButton("ВЕРТИКАЛЬНО")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def count_menu():
    keyboard = [[KeyboardButton("2 ФОТО")], [KeyboardButton("3 ФОТО")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def continue_button():
    keyboard = [[KeyboardButton("ПРОДОЛЖИТЬ")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def start_session(update: Update, user_id):
    user_state[user_id] = WAITING_DIRECTION
    user_settings[user_id] = {}
    user_photos[user_id] = []
    user_descriptions[user_id] = []
    await update.message.reply_text("Выбери направление сшивания:", reply_markup=main_menu())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_session(update, update.effective_user.id)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().lower()
    state = user_state.get(user_id)

    if text == "продолжить":
        await start_session(update, user_id)
        return

    if state == WAITING_DIRECTION:
        if "горизонт" in text:
            user_settings[user_id]["direction"] = "horizontal"
        elif "вертикал" in text:
            user_settings[user_id]["direction"] = "vertical"
        else:
            await update.message.reply_text("Выбери: ГОРИЗОНТАЛЬНО или ВЕРТИКАЛЬНО.")
            return
        user_state[user_id] = WAITING_COUNT
        await update.message.reply_text("Сколько фото хочешь сшить?", reply_markup=count_menu())

    elif state == WAITING_COUNT:
        if "2" in text:
            user_settings[user_id]["count"] = 2
        elif "3" in text:
            user_settings[user_id]["count"] = 3
        else:
            await update.message.reply_text("Выбери: 2 ФОТО или 3 ФОТО.")
            return
        user_state[user_id] = WAITING_PHOTOS
        await update.message.reply_text("Отправь фото #1:", reply_markup=ReplyKeyboardRemove())

    elif state == WAITING_DESCRIPTION:
        user_descriptions[user_id].append(text)
        if len(user_descriptions[user_id]) < user_settings[user_id]["count"]:
            await update.message.reply_text(f"Введи описание для фото #{len(user_descriptions[user_id]) + 1}:")
        else:
            await update.message.reply_text("Создаю коллаж, подожди...")
            await send_stitched_image(update, user_id)
            await update.message.reply_text("Готово! Хочешь ещё?", reply_markup=continue_button())
            user_state[user_id] = None


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id)

    if state != WAITING_PHOTOS:
        await update.message.reply_text("Нажми /start или 'ПРОДОЛЖИТЬ', чтобы начать.")
        return

    photo_file = await update.message.photo[-1].get_file()
    byte_data = await photo_file.download_as_bytearray()
    user_photos[user_id].append(BytesIO(byte_data))

    if len(user_photos[user_id]) < user_settings[user_id]["count"]:
        await update.message.reply_text(f"Принято! Отправь фото #{len(user_photos[user_id]) + 1}:")
    else:
        user_state[user_id] = WAITING_DESCRIPTION
        await update.message.reply_text("Теперь введи описание для фото #1:")


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


async def send_stitched_image(update: Update, user_id):
    images = user_photos[user_id]
    descriptions = user_descriptions[user_id]
    direction = user_settings[user_id].get("direction", "horizontal")

    stitched = stitch_images(images, direction)
    file_name = f"collage_{user_id}.jpg"
    with open(file_name, "wb") as f:
        f.write(stitched.getbuffer())

    try:
        response = upload_file(file_name)
        url = f"https://telegra.ph{response[0]}"
        desc_html = "<br><br>".join([f"<b>Фото {i+1}:</b><br>{desc}" for i, desc in enumerate(descriptions)])

        page = telegraph.create_page(
            title="Коллаж",
            html_content=f'<img src="{url}"><br><br>{desc_html}'
        )
        await update.message.reply_text(f"🖼 Ссылка на коллаж: https://telegra.ph/{page['path']}")
    except Exception as e:
        logger.error(f"Ошибка загрузки в Telegraph: {e}")
        await update.message.reply_text("❌ Ошибка при загрузке в Telegraph.")


async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    print("✅ Бот запущен...")
    await app.run_polling()


if __name__ == '__main__':
    asyncio.run(main())
