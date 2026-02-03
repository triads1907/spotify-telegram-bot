"""
Обработчики команд /start и /help
"""
from telegram import Update
from telegram.ext import ContextTypes
from utils.keyboards import KeyboardBuilder
import config


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_obj = update.effective_user
    db = context.bot_data.get('db')
    
    # Получаем/создаем пользователя и его настройки
    lang = "ru"
    if db:
        user_db = await db.get_or_create_user(
            user_id=user_obj.id,
            username=user_obj.username,
            first_name=user_obj.first_name,
            last_name=user_obj.last_name
        )
        lang = user_db.language
    
    # Отправляем приветственное сообщение
    keyboard = KeyboardBuilder.main_menu(lang)
    
    # В конфиге WELCOME_MESSAGE только на русском, 
    # если язык английский, можно использовать строку из strings.py или перевести
    welcome_text = config.WELCOME_MESSAGE
    if lang == "en":
        welcome_text = welcome_text.replace("Привет!", "Hello!").replace("Я помогу тебе скачать музыку из Spotify.", "I can help you download music from Spotify.")
        # Или можно добавить welcome_msg в strings.py, но пока так
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=keyboard,
        parse_mode='HTML'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    user_id = update.effective_user.id
    db = context.bot_data.get('db')
    lang = "ru"
    if db:
        user = await db.get_or_create_user(user_id, update.effective_user)
        lang = user.language
        
    keyboard = KeyboardBuilder.back_button(lang)
    
    help_text = config.HELP_MESSAGE
    if lang == "en":
        help_text = "📖 <b>How to use the bot:</b>\n\n" \
                    "1. Find a track on <b>Spotify</b>\n" \
                    "2. Copy the link to the track\n" \
                    "3. Send the link to this bot\n" \
                    "4. Wait for the download and enjoy! 🎧"
                    
    await update.message.reply_text(
        help_text,
        reply_markup=keyboard,
        parse_mode='HTML',
        disable_web_page_preview=True
    )

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Генерация ссылки для входа в веб-интерфейс"""
    user_id = update.effective_user.id
    db = context.bot_data.get('db')
    import secrets
    
    # Генерируем временный токен
    token = secrets.token_urlsafe(24)
    
    # Сохраняем токен в БД
    if db:
        await db.create_auth_token(user_id, token)
    
    # Ссылка на веб-интерфейс (берем из конфига или дефолт)
    web_url = getattr(config, 'WEB_APP_URL', 'http://localhost:5000')
    auth_url = f"{web_url}/?auth={token}"
    
    text = f"🔗 <b>Вход в веб-интерфейс</b>\n\n" \
           f"Ваша персональная ссылка для входа (действует 5 минут):\n" \
           f"<code>{auth_url}</code>\n\n" \
           f"<i>Никому не передавайте эту ссылку!</i>"
           
    await update.message.reply_text(text, parse_mode='HTML', disable_web_page_preview=True)
