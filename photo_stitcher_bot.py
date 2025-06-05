import logging
import asyncio
import os
from io import BytesIO
from PIL import Image
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegraph import upload_file
import nest_asyncio

nest_asyncio.apply()

TOKEN = '8061285829:AAFMjY72I6W3yKDtbR5MaIT72F-R61wFcAM'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}
user_settings = {}
user_photos = {}
media_group_photos = {}

WAITING_DIRECTION = "waiting_direction"
WAITING_DESCRIPTION = "waiting_description"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = WAITING_DIRECTION
    user_settings[user_id] = {}
    user_photos[user_id] = []
    media_group_photos[user_id] = []

    keyboard = [
        [KeyboardButton("🔹 Горизонтально")],
        [KeyboardButton("🔻 Вертикально")]
    ]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text(
        "📸 Отправь 2 или 3 фото **одним сообщением** (альбомом),\nа потом выбери способ сшивания.",
        reply_markup=markup
    )


async def handle_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = update.message

    if msg.media_group_id:
        if user_id not in media_group_photos:
            media_group_photos[user_id] = []
        photo_file = await msg.photo[-1].get_file()
        data = await photo_file.download_as_bytearray()
        media_group_photos[user_id].append(BytesIO(data))

        await asyncio.sleep(1) 
        return

  
    await msg.reply_text("⚠️ Пожалуйста, отправь сразу 2 или 3 фото **одним сообщением** (альбомом).")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id)
    text = update.message.text.lower()

    if state == WAITING_DIRECTION:
        if "гориз" in text:
            user_settings[user_id]["direction"] = "horizontal"
        elif "вертик" in text:
            user_settings[user_id]["direction"] = "vertical"
        else:
            await update.message.reply_text("Выбери: 🔹 Горизонтально или 🔻 Вертикально")
            return

      
        if user_id not in media_group_photos or not (2 <= len(media_group_photos[user_id]) <= 3):
            await update.message.reply_text("⚠️ Сначала отправь 2 или 3 фото одним сообщением.")
            return

        user_photos[user_id] = media_group_photos[user_id]
        media_group_photos[user_id] = []
        user_state[user_id] = WAITING_DESCRIPTION
        await update.message.reply_text("🖋️ Напиши описание к коллажу:", reply_markup=ReplyKeyboardRemove())

    elif state == WAITING_DESCRIPTION:
        await update.message.reply_text("🔧 Обрабатываю изображение...")
        await send_collage(update, context, text)
        user_state[user_id] = None
        user_photos[user_id] = []
        user_settings[user_id] = {}


async def send_collage(update, context, description):
    user_id = update.effective_user.id
    images = user_photos.get(user_id, [])
    direction = user_settings[user_id].get("direction", "horizontal")

    if not images:
        await update.message.reply_text("❌ Фото не найдены.")
        return

    stitched = stitch_images(images, direction)
    filename = f"collage_{user_id}.jpg"
    with open(filename, "wb") as f:
        f.write(stitched.getbuffer())

    try:
        response = upload_file(filename)
        url = f"https://telegra.ph{response[0]}"
        await update.message.reply_text(
            f"✅ Готово!\n🔗 Ссылка на коллаж: {url}\n\n📝 Описание:\n{description}"
        )
    except Exception as e:
        logger.error(f"Telegraph error: {e}")
        await update.message.reply_text("❌ Ошибка при загрузке в Telegraph. Убедитесь, что размер файла < 5MB.")
    finally:
        if os.path.exists(filename):
            os.remove(filename)


def stitch_images(images, direction):
    pil_images = [Image.open(img).convert("RGB") for img in images]

    if direction == 'horizontal':
        max_h = max(i.height for i in pil_images)
        resized = [i.resize((int(i.width * max_h / i.height), max_h)) for i in pil_images]
        total_w = sum(i.width for i in resized)
        result = Image.new('RGB', (total_w, max_h))
        x = 0
        for i in resized:
            result.paste(i, (x, 0))
            x += i.width
    else:
        max_w = max(i.width for i in pil_images)
        resized = [i.resize((max_w, int(i.height * max_w / i.width))) for i in pil_images]
        total_h = sum(i.height for i in resized)
        result = Image.new('RGB', (max_w, total_h))
        y = 0
        for i in resized:
            result.paste(i, (0, y))
            y += i.height

    result = result.resize((result.width // 2, result.height // 2))
    output = BytesIO()
    result.save(output, format='JPEG', quality=30, optimize=True)
    output.seek(0)
    return output


async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_photos))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("✅ Бот запущен...")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
