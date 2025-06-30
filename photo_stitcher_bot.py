import os
import requests
from PIL import Image
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = '8061285829:AAFMjY72I6W3yKDtbR5MaIT72F-R61wFcAM'
IMGBB_API_KEY = '324d90875472bf6af97d09df17726bf4'
TEMP_DIR = 'temp'
user_state = {}

if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_state:
        user_state[user_id] = {'mode': None, 'photos': [], 'caption': None, 'orientation': 'horizontal'}
    else:
        clear_user_files(user_id)
        user_state[user_id].update({'photos': [], 'caption': None})
    keyboard = [[KeyboardButton("📌 Сшить фото в коллаж")], [KeyboardButton("🔗 Получить ссылку на фото")]]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "👋 Привет! Я могу сшивать фото или давать ссылку на отправленное фото. Выбери режим:",
        reply_markup=markup
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = (update.message.text or '').strip()
    state = user_state.get(user_id)
    if not state:
        user_state[user_id] = {'mode': None, 'photos': [], 'caption': None, 'orientation': 'horizontal'}
        state = user_state[user_id]

    if not state.get('mode'):
        if text == "📌 Сшить фото в коллаж":
            state['mode'] = 'collage'
            await update.message.reply_text("Отправь 3 фото и комментарий", reply_markup=ReplyKeyboardRemove())
            return
        elif text == "🔗 Получить ссылку на фото":
            state['mode'] = 'upload'
            await update.message.reply_text("Отправь фото с подписью")
            return
        else:
            keyboard = [[KeyboardButton("📌 Сшить фото в коллаж")], [KeyboardButton("🔗 Получить ссылку на фото")]]
            markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text("Выбери режим:", reply_markup=markup)
            return

    mode = state.get('mode')

    if mode == 'upload':
        if update.message.photo and update.message.caption:
            photo = update.message.photo[-1]
            file = await photo.get_file()
            file_path = f"{TEMP_DIR}/{user_id}_upload.jpg"
            await file.download_to_drive(file_path)
            await update.message.reply_text(f"Загружено, размер: {os.path.getsize(file_path)} байт")
            
            f = open(file_path, 'rb')
            res = requests.post(
                "https://api.imgbb.com/1/upload",
                data={"key": IMGBB_API_KEY},
                files={"image": f}
            )
            f.close()

            if res.ok:
                url = res.json()["data"]["url"]
                clean_caption = update.message.caption.strip().replace('\r', '')
                await update.message.reply_photo(photo=file_path)
                await update.message.reply_text(f"{clean_caption}\n{url}")
            else:
                await update.message.reply_text(f"Ошибка загрузки: {res.status_code}\n{res.text}")
            return

    if mode == 'collage':
        if update.message.photo:
            photo = update.message.photo[-1]
            file = await photo.get_file()
            file_path = f"{TEMP_DIR}/{user_id}_{len(state['photos'])}.jpg"
            await file.download_to_drive(file_path)
            state['photos'].append(file_path)
            if update.message.caption:
                state['caption'] = update.message.caption
            if len(state['photos']) == 3 and state.get('caption'):
                await process_collage(update, user_id)
        elif text and not update.message.photo:
            state['caption'] = text
            if len(state['photos']) == 3:
                await process_collage(update, user_id)
        return

def clear_user_files(user_id):
    try:
        for p in user_state[user_id].get('photos', []):
            if os.path.exists(p): os.remove(p)
        path1 = f"{TEMP_DIR}/{user_id}_upload.jpg"
        path2 = f"{TEMP_DIR}/collage_{user_id}.jpg"
        if os.path.exists(path1): os.remove(path1)
        if os.path.exists(path2): os.remove(path2)
    except: pass

async def process_collage(update: Update, user_id: int):
    state = user_state[user_id]
    if not state.get('caption'):
        return
    try:
        orientation = state.get('orientation', 'horizontal')
        description = state.get('caption')
        raw_images = [Image.open(p).convert("RGB") for p in state['photos']]
        if orientation == 'horizontal':
            h = min(img.height for img in raw_images)
            images = [img.resize((int(img.width * h / img.height), h), Image.LANCZOS) for img in raw_images]
            collage = Image.new('RGB', (sum(img.width for img in images), h))
            offset = 0
            for img in images:
                collage.paste(img, (offset, 0))
                offset += img.width
        else:
            w = min(img.width for img in raw_images)
            images = [img.resize((w, int(img.height * w / img.width)), Image.LANCZOS) for img in raw_images]
            collage = Image.new('RGB', (w, sum(img.height for img in images)))
            offset = 0
            for img in images:
                collage.paste(img, (0, offset))
                offset += img.height
        target_width = 800
        if collage.width > target_width:
            ratio = target_width / collage.width
            collage = collage.resize((target_width, int(collage.height * ratio)), Image.LANCZOS)
        collage_path = f"{TEMP_DIR}/collage_{user_id}.jpg"
        collage.save(collage_path, optimize=True, quality=85)

        f = open(collage_path, 'rb')
        res = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": IMGBB_API_KEY},
            files={"image": f}
        )
        f.close()

        if res.ok:
            url = res.json()["data"]["url"]
            clean_description = description.strip().replace('\r', '')
            await update.message.reply_text(f"{clean_description}\n{url}")
        else:
            await update.message.reply_text(f"Ошибка загрузки: {res.status_code}\n{res.text}")

        clear_user_files(user_id)
        user_state[user_id].update({'photos': [], 'caption': None})
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

if __name__ == '__main__':
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL, message_handler))
    app.run_polling()
