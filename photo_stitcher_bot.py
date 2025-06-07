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
    reset_user(user_id)
    keyboard = [[KeyboardButton("📌 Сшить фото в коллаж")], [KeyboardButton("🔗 Получить ссылку на фото")]]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "👋 Привет! Я могу сшивать фото или давать ссылку на отправленное фото. Выбери режим:",
        reply_markup=markup
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = (update.message.text or '').strip()

    if text == "📌 Сшить фото в коллаж":
        user_state[user_id] = {'mode': 'collage'}
        await show_photo_count_options(update)
        return

    if text == "🔗 Получить ссылку на фото":
        user_state[user_id] = {'mode': 'upload'}
        await update.message.reply_text("📥 Отправь фото с подписью, и я верну тебе ссылку и описание")
        return

    if user_id not in user_state:
        keyboard = [[KeyboardButton("📌 Сшить фото в коллаж")], [KeyboardButton("🔗 Получить ссылку на фото")]]
        markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Пожалуйста, сначала выбери режим:", reply_markup=markup)
        return

    mode = user_state[user_id].get('mode')

    if mode == 'upload':
        if update.message.photo and update.message.caption:
            photo = update.message.photo[-1]
            file = await photo.get_file()
            file_path = f"{TEMP_DIR}/{user_id}_upload.jpg"
            await file.download_to_drive(file_path)
            with open(file_path, 'rb') as f:
                res = requests.post(
                    "https://api.imgbb.com/1/upload",
                    params={"key": IMGBB_API_KEY},
                    files={"image": f}
                )
            if res.ok:
                url = res.json()["data"]["url"]
                clean_caption = update.message.caption.strip().replace('\n', ' ').replace('\r', '')
                with open(file_path, 'rb') as img:
                    await update.message.reply_photo(photo=img, caption=f"{clean_caption} {url}")
            else:
                await update.message.reply_text("❌ Ошибка при загрузке изображения")
            return

    if mode == 'collage':
        if "новый" in text.lower() and "коллаж" in text.lower():
            reset_user(user_id)
            await show_photo_count_options(update)
            return

        if text.startswith("2️⃣") or text.startswith("3️⃣"):
            user_state[user_id].update({
                'count': int(text[0]),
                'photos': [],
                'awaiting_description': False,
                'orientation': None
            })
            keyboard = [[KeyboardButton("↔️ Горизонтально"), KeyboardButton("↕️ Вертикально")]]
            markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text("📐 Как расположить фото в коллаже?", reply_markup=markup)
            return

        if text in ["↔️ Горизонтально", "↕️ Вертикально"]:
            user_state[user_id]['orientation'] = 'horizontal' if "↔️" in text else 'vertical'
            await update.message.reply_text(
                f"📥 Жду 1/{user_state[user_id]['count']} фото...",
                reply_markup=ReplyKeyboardRemove()
            )
            return

        if update.message.photo:
            state = user_state[user_id]
            photo = update.message.photo[-1]
            file = await photo.get_file()
            file_path = f"{TEMP_DIR}/{user_id}_{len(state['photos'])}.jpg"
            await file.download_to_drive(file_path)
            state['photos'].append(file_path)

            received = len(state['photos'])
            total = state['count']

            if received < total:
                await update.message.reply_text(f"📥 Жду {received + 1}/{total} фото...")
            else:
                state['awaiting_description'] = True
                await update.message.reply_text("✍️ Введи описание для коллажа:")
            return

        if user_state[user_id].get('awaiting_description'):
            await update.message.reply_text("⏳ Обрабатываю коллаж...")
            await process_collage(update, user_id, text)

async def show_photo_count_options(update: Update):
    keyboard = [[KeyboardButton("2️⃣ Сшить 2 фото")], [KeyboardButton("3️⃣ Сшить 3 фото")]]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("🔢 Сколько фото ты хочешь сшить?", reply_markup=markup)

def reset_user(user_id):
    if user_id in user_state:
        try:
            for p in user_state[user_id].get('photos', []):
                if os.path.exists(p): os.remove(p)
            path1 = f"{TEMP_DIR}/{user_id}_upload.jpg"
            path2 = f"{TEMP_DIR}/collage_{user_id}.jpg"
            if os.path.exists(path1): os.remove(path1)
            if os.path.exists(path2): os.remove(path2)
        except: pass
        del user_state[user_id]

async def process_collage(update: Update, user_id: int, description: str):
    orientation = user_state[user_id].get('orientation', 'horizontal')
    raw_images = [Image.open(p).convert("RGB") for p in user_state[user_id]['photos']]

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

    with open(collage_path, 'rb') as f:
        res = requests.post(
            "https://api.imgbb.com/1/upload",
            params={"key": IMGBB_API_KEY},
            files={"image": f}
        )

    if res.ok:
        url = res.json()["data"]["url"]
        clean_description = description.strip().replace('\n', ' ').replace('\r', '')
        with open(collage_path, 'rb') as img:
            await update.message.reply_photo(photo=img, caption=f"{clean_description} {url}")
        keyboard = [[KeyboardButton("🔁 Сделать новый коллаж")]]
        markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("✅ Готово! Хочешь сделать ещё?", reply_markup=markup)
    else:
        await update.message.reply_text("❌ Ошибка при загрузке изображения.")

    reset_user(user_id)

if __name__ == '__main__':
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL, message_handler))
    app.run_polling()
