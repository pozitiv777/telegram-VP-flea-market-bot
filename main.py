import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import os
import time

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Импорт конфигурации
try:
    from config import BOT_TOKEN, ADMIN_ID
except ImportError:
    print("❌ Ошибка: Создайте файл config.py с BOT_TOKEN и ADMIN_ID")
    exit(1)

# Инициализация базы данных
def init_db():
    try:
        conn = sqlite3.connect('fleamarket.db', check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone TEXT,
                registered_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                price REAL,
                category TEXT,
                photo_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        print("✅ База данных инициализирована")
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")

# Регистрация пользователя
def register_user(user_id, username, first_name, last_name):
    try:
        conn = sqlite3.connect('fleamarket.db', check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка регистрации пользователя: {e}")

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        register_user(user.id, user.username, user.first_name, user.last_name)
        
        keyboard = [
            ["📦 Добавить объявление", "📋 Мои объявления"],
            ["🔍 Поиск объявлений", "ℹ️ Помощь"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "👋 Добро пожаловать в барахолку Верхней Пышмы!\n\n"
            "Здесь вы можете:\n"
            "• 📦 Продавать вещи\n"
            "• 🔍 Покупать товары\n"
            "• 💰 Находить выгодные предложения\n\n"
            "Выберите действие:",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Ошибка в команде /start: {e}")

# Команда для добавления объявления
async def add_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['creating_ad'] = True
        context.user_data['ad_data'] = {}
        
        await update.message.reply_text(
            "📝 Создаем новое объявление!\n\n"
            "Введите название товара:"
        )
    except Exception as e:
        logger.error(f"Ошибка в add_ad: {e}")

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message or not update.message.text:
            return
            
        user_data = context.user_data
        
        if user_data.get('creating_ad'):
            ad_data = user_data.get('ad_data', {})
            
            if 'title' not in ad_data:
                ad_data['title'] = update.message.text
                await update.message.reply_text("📝 Введите описание товара:")
            
            elif 'description' not in ad_data:
                ad_data['description'] = update.message.text
                await update.message.reply_text("💰 Введите цену товара (только цифры):")
            
            elif 'price' not in ad_data:
                try:
                    price = float(update.message.text.replace(',', '.'))
                    ad_data['price'] = price
                    
                    keyboard = [
                        ["👕 Одежда", "👟 Обувь"],
                        ["📱 Электроника", "🏠 Для дома"],
                        ["🎮 Хобби", "📚 Книги"],
                        ["🚗 Авто", "⚽ Другое"]
                    ]
                    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                    
                    await update.message.reply_text(
                        "📂 Выберите категорию товара:",
                        reply_markup=reply_markup
                    )
                    
                except ValueError:
                    await update.message.reply_text("❌ Пожалуйста, введите корректную цену (только цифры):")
            
            elif 'category' not in ad_data:
                ad_data['category'] = update.message.text
                await update.message.reply_text(
                    "📸 Пришлите фото товара (или отправьте 'пропустить' чтобы продолжить без фото):",
                    reply_markup=ReplyKeyboardMarkup([["пропустить"]], resize_keyboard=True)
                )
            
            elif 'photo' not in ad_data:
                if update.message.text and update.message.text.lower() == 'пропустить':
                    ad_data['photo'] = None
                    await save_ad(update, context)
                else:
                    await update.message.reply_text("❌ Пожалуйста, отправьте фото или 'пропустить'")
            
            user_data['ad_data'] = ad_data
            return
        
        if user_data.get('searching'):
            await search_ads(update, context)
            return
        
        await update.message.reply_text("Выберите действие из меню:")
    except Exception as e:
        logger.error(f"Ошибка в handle_message: {e}")

# Обработка фото
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_data = context.user_data
        
        if user_data.get('creating_ad') and user_data.get('ad_data', {}).get('category'):
            ad_data = user_data['ad_data']
            ad_data['photo'] = update.message.photo[-1].file_id
            await save_ad(update, context)
    except Exception as e:
        logger.error(f"Ошибка в handle_photo: {e}")

# Сохранение объявления
async def save_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_data = context.user_data
        ad_data = user_data.get('ad_data', {})
        user = update.effective_user
        
        if all(key in ad_data for key in ['title', 'description', 'price', 'category']):
            conn = sqlite3.connect('fleamarket.db', check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO ads (user_id, title, description, price, category, photo_id, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
            ''', (user.id, ad_data['title'], ad_data['description'], 
                  ad_data['price'], ad_data['category'], ad_data.get('photo')))
            
            ad_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            await notify_admin(context, ad_id, ad_data, user)
            
            user_data.pop('creating_ad', None)
            user_data.pop('ad_data', None)
            
            keyboard = [
                ["📦 Добавить объявление", "📋 Мои объявления"],
                ["🔍 Поиск объявлений", "ℹ️ Помощь"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            await update.message.reply_text(
                "✅ Объявление отправлено на модерацию!\n"
                "Обычно это занимает несколько часов.\n\n"
                "Вы получите уведомление, когда объявление будет опубликовано.",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text("❌ Ошибка при создании объявления. Попробуйте снова.")
    except Exception as e:
        logger.error(f"Ошибка в save_ad: {e}")

# Уведомление администратора
async def notify_admin(context: ContextTypes.DEFAULT_TYPE, ad_id: int, ad_data: dict, user):
    try:
        keyboard = [
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{ad_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{ad_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            "🆕 Новое объявление на модерацию!\n\n"
            f"📌 ID: {ad_id}\n"
            f"👤 Пользователь: @{user.username or 'нет'} ({user.first_name})\n"
            f"📦 Товар: {ad_data['title']}\n"
            f"📝 Описание: {ad_data['description']}\n"
            f"💰 Цена: {ad_data['price']} руб.\n"
            f"📂 Категория: {ad_data['category']}"
        )
        
        if ad_data.get('photo'):
            await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=ad_data['photo'],
                caption=message_text,
                reply_markup=reply_markup
            )
        else:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=message_text,
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления администратору: {e}")

# Обработка модерации
async def handle_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        ad_id = int(data.split('_')[1])
        
        conn = sqlite3.connect('fleamarket.db', check_same_thread=False)
        cursor = conn.cursor()
        
        if data.startswith('approve'):
            cursor.execute('UPDATE ads SET status = "approved" WHERE id = ?', (ad_id,))
            status_text = "одобрено"
            
            cursor.execute('SELECT user_id FROM ads WHERE id = ?', (ad_id,))
            result = cursor.fetchone()
            if result:
                user_id = result[0]
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"✅ Ваше объявление №{ad_id} было одобрено и опубликовано!"
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления пользователю: {e}")
        
        elif data.startswith('reject'):
            cursor.execute('UPDATE ads SET status = "rejected" WHERE id = ?', (ad_id,))
            status_text = "отклонено"
            
            cursor.execute('SELECT user_id FROM ads WHERE id = ?', (ad_id,))
            result = cursor.fetchone()
            if result:
                user_id = result[0]
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"❌ Ваше объявление №{ad_id} было отклонено модератором."
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления пользователю: {e}")
        
        conn.commit()
        conn.close()
        
        await query.edit_message_text(f"✅ Объявление №{ad_id} {status_text}!")
    except Exception as e:
        logger.error(f"Ошибка в handle_moderation: {e}")

# Мои объявления
async def my_ads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        
        conn = sqlite3.connect('fleamarket.db', check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, title, description, price, category, status, created_at 
            FROM ads WHERE user_id = ? ORDER BY created_at DESC
        ''', (user.id,))
        
        ads = cursor.fetchall()
        conn.close()
        
        if not ads:
            await update.message.reply_text("📭 У вас пока нет объявлений.")
            return
        
        for ad in ads:
            ad_id, title, description, price, category, status, created_at = ad
            
            status_emoji = {
                'pending': '⏳',
                'approved': '✅',
                'rejected': '❌'
            }.get(status, '❓')
            
            message = (
                f"📦 Объявление №{ad_id}\n"
                f"📌 {title}\n"
                f"📝 {description}\n"
                f"💰 {price} руб.\n"
                f"📂 {category}\n"
                f"📅 {created_at[:10]}\n"
                f"Статус: {status_emoji} {status}\n"
            )
            
            await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Ошибка в my_ads: {e}")

# Поиск объявлений
async def search_ads_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['searching'] = True
        await update.message.reply_text(
            "🔍 Введите ключевые слова для поиска:\n"
            "(название товара, категория и т.д.)"
        )
    except Exception as e:
        logger.error(f"Ошибка в search_ads_command: {e}")

async def search_ads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        search_term = f"%{update.message.text}%"
        
        conn = sqlite3.connect('fleamarket.db', check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT a.id, a.title, a.description, a.price, a.category, a.photo_id, 
                   u.username, u.first_name, a.created_at
            FROM ads a
            JOIN users u ON a.user_id = u.user_id
            WHERE a.status = 'approved' 
            AND (a.title LIKE ? OR a.description LIKE ? OR a.category LIKE ?)
            ORDER BY a.created_at DESC
            LIMIT 20
        ''', (search_term, search_term, search_term))
        
        ads = cursor.fetchall()
        conn.close()
        
        context.user_data['searching'] = False
        
        if not ads:
            await update.message.reply_text("😔 По вашему запросу ничего не найдено.")
            return
        
        await update.message.reply_text(f"🔍 Найдено объявлений: {len(ads)}")
        
        for ad in ads:
            ad_id, title, description, price, category, photo_id, username, first_name, created_at = ad
            
            contact_info = f"@{username}" if username else first_name
            
            message = (
                f"📦 {title}\n"
                f"📝 {description}\n"
                f"💰 {price} руб.\n"
                f"📂 {category}\n"
                f"👤 {contact_info}\n"
                f"📅 {created_at[:10]}\n"
                f"ID: {ad_id}"
            )
            
            try:
                if photo_id:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=photo_id,
                        caption=message
                    )
                else:
                    await update.message.reply_text(message)
            except Exception as e:
                logger.error(f"Ошибка отправки объявления: {e}")
                await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Ошибка в search_ads: {e}")

# Помощь
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        help_text = (
            "ℹ️ Помощь по использованию барахолки\n\n"
            "Добавить объявление:\n"
            "1. Нажмите '📦 Добавить объявление'\n"
            "2. Следуйте инструкциям бота\n"
            "3. Дождитесь модерации\n\n"
            "Поиск товаров:\n"
            "1. Нажмите '🔍 Поиск объявлений'\n"
            "2. Введите ключевые слова\n"
            "3. Выберите подходящее объявление\n\n"
            "Правила:\n"
            "• Запрещена продажа запрещенных товаров\n"
            "• Будьте вежливы с другими пользователями\n"
            "• Описывайте товар честно\n\n"
            "По вопросам работы бота обращайтесь к администратору."
        )
        
        await update.message.reply_text(help_text)
    except Exception as e:
        logger.error(f"Ошибка в help_command: {e}")

# Статистика для админа
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ У вас нет прав для этой команды.")
            return
        
        conn = sqlite3.connect('fleamarket.db', check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM ads WHERE status = "pending"')
        pending = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM ads WHERE status = "approved"')
        approved = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users')
        users = cursor.fetchone()[0]
        
        conn.close()
        
        stats_text = (
            "📊 Статистика барахолки\n\n"
            f"👥 Пользователей: {users}\n"
            f"⏳ Ожидают модерации: {pending}\n"
            f"✅ Опубликовано: {approved}\n"
        )
        
        await update.message.reply_text(stats_text)
    except Exception as e:
        logger.error(f"Ошибка в admin_stats: {e}")

def main():
    try:
        print("🔄 Инициализация бота...")
        init_db()
        
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Обработчики команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("stats", admin_stats))
        
        # Обработчики callback кнопок
        application.add_handler(CallbackQueryHandler(handle_moderation, pattern="^(approve|reject)_"))
        
        # Обработчики кнопок меню
        application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📦 Добавить объявление$"), add_ad))
        application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📋 Мои объявления$"), my_ads))
        application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^🔍 Поиск объявлений$"), search_ads_command))
        application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^ℹ️ Помощь$"), help_command))
        
        # Обработчики контента
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        print("✅ Бот запущен...")
        print("🤖 Ищите бота в Telegram по username")
        
        # Убираем input() для облачной среды
        application.run_polling()
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        # Убираем input() для облачной среды
        time.sleep(5)  # Пауза чтобы увидеть ошибку

if __name__ == '__main__':
    main()
