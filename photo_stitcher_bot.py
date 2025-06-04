import logging
from io import BytesIO
from PIL import Image
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CommandHandler, ContextTypes
import nest_asyncio
import asyncio

nest_asyncio.apply()

TOKEN = '8061285829:AAFMjY72I6W3yKDtbR5MaIT72F-R61wFcAM' 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_photos = {}          # user_id -> list of BytesIO
stitch_direction = {}     # user_id -> 'horizontal' or 'vertical'


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Отправь мне 2 или 3 фото (по одному или альбомом), и потом используй /stitch для сшивания.\n"
        "Команды:\n/horizontal — шить по горизонтали\n/vertical — шить по вертикали"
    )


async def set_horizontal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stitch_direction[update.effective_user.id] = 'horizontal'
    await update.message.reply_text("📸 Режим сшивания установлен: по горизонтали.")


async def set_vertical(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stitch_direction[update.effective_user.id] = 'vertical'
    await update.message.reply_text("📸 Режим сшивания установлен: по вертикали.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photo_file = await update.message.photo[-1].get_file()
    byte_data = await photo_file.download_as_bytearray()
    photo = BytesIO(byte_data)

    if user_id not in user_photos:
        user_photos[user_id] = []

    user_photos[user_id].append(photo)
    count = len(user_photos[user_id])

    if count > 3:
        user_photos[user_id] = []
        await update.message.reply_text("⚠️ Можно отправить только 2 или 3 фото. Всё сброшено. Начни заново.")
    else:
        await update.message.reply_text(f"📷 Фото принято! Загружено: {count}/3.\nКогда будешь готов — введи /stitch.")


async def stitch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    images = user_photos.get(user_id, [])

    if len(images) not in [2, 3]:
        await update.message.reply_text("❗ Нужно загрузить ровно 2 или 3 фото перед сшиванием.")
        return

    await update.message.reply_text("🧵 Обрабатываю, подожди...")
    await send_stitched_image(update, context, user_id)


async def send_stitched_image(update, context, user_id):
    images = user_photos[user_id][:3]
    direction = stitch_direction.get(user_id, 'horizontal')
    logger.info(f"🧵 Сшиваю {len(images)} изображений в режиме {direction} для user_id={user_id}")
    try:
        stitched = stitch_images(images, direction)
        await update.message.reply_photo(photo=stitched)
    except Exception as e:
        logger.error(f"❌ Ошибка при сшивании изображений: {e}")
        await update.message.reply_text("Произошла ошибка при сшивании изображений.")
    finally:
        user_photos[user_id] = []


def stitch_images(images, direction='horizontal'):
    pil_images = [Image.open(img).convert("RGB") for img in images]

    if direction == 'horizontal':
        max_height = max(img.height for img in pil_images)
        resized = [img.resize((int(img.width * max_height / img.height), max_height)) for img in pil_images]
    else:
        max_width = max(img.width for img in pil_images)
        resized = [img.resize((max_width, int(img.height * max_width / img.width))) for img in pil_images]

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

    output = BytesIO()
    result.save(output, format='JPEG')
    output.seek(0)
    return output


async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("horizontal", set_horizontal))
    app.add_handler(CommandHandler("vertical", set_vertical))
    app.add_handler(CommandHandler("stitch", stitch_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("✅ Бот запущен...")
    await app.run_polling()


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())
