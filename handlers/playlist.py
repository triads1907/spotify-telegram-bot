"""
Обработчики управления плейлистами
"""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from utils.keyboards import KeyboardBuilder, get_track_actions_keyboard
from services.message_builder import MessageBuilder
import config

# Состояния для ConversationHandler
WAITING_PLAYLIST_NAME, WAITING_PLAYLIST_DESCRIPTION = range(2)


async def my_playlists_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /myplaylists"""
    user_id = update.effective_user.id
    db = context.bot_data.get('db')
    
    if not db:
        await update.message.reply_text("❌ База данных недоступна")
        return
    
    # Получаем плейлисты пользователя
    playlists = await db.get_user_playlists(user_id)
    
    if not playlists:
        message = """
📋 <b>Мои плейлисты</b>

У вас пока нет плейлистов.
Создайте свой первый плейлист!
"""
        keyboard = KeyboardBuilder.user_playlists([])
        await update.message.reply_text(
            message,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return
    
    # Формируем сообщение со списком плейлистов
    message = "📋 <b>Мои плейлисты:</b>\n\n"
    
    for i, playlist in enumerate(playlists, 1):
        track_count = await db.get_playlist_track_count(playlist.id)
        message += f"{i}. <b>{playlist.name}</b> ({track_count} треков)\n"
    
    keyboard = KeyboardBuilder.user_playlists(playlists)
    
    await update.message.reply_text(
        message,
        reply_markup=keyboard,
        parse_mode='HTML'
    )


async def create_playlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания плейлиста"""
    await update.message.reply_text(
        "📋 <b>Создание нового плейлиста</b>\n\n"
        "Введите название плейлиста (до 100 символов):\n\n"
        "Или отправьте /cancel для отмены",
        parse_mode='HTML'
    )
    return WAITING_PLAYLIST_NAME


async def receive_playlist_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение названия плейлиста"""
    playlist_name = update.message.text.strip()
    
    if len(playlist_name) > config.MAX_PLAYLIST_NAME_LENGTH:
        await update.message.reply_text(
            f"❌ Название слишком длинное. Максимум {config.MAX_PLAYLIST_NAME_LENGTH} символов.\n"
            "Попробуйте еще раз:",
            parse_mode='HTML'
        )
        return WAITING_PLAYLIST_NAME
    
    # Сохраняем название в контексте
    context.user_data['new_playlist_name'] = playlist_name
    
    await update.message.reply_text(
        f"✅ Название: <b>{playlist_name}</b>\n\n"
        "Теперь введите описание плейлиста (необязательно):\n\n"
        "Или отправьте /skip чтобы пропустить",
        parse_mode='HTML'
    )
    return WAITING_PLAYLIST_DESCRIPTION


async def receive_playlist_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение описания плейлиста"""
    description = update.message.text.strip() if update.message.text != '/skip' else None
    
    # Создаем плейлист
    user_id = update.effective_user.id
    db = context.bot_data.get('db')
    playlist_name = context.user_data.get('new_playlist_name')
    
    try:
        playlist = await db.create_playlist(
            user_id=user_id,
            name=playlist_name,
            description=description
        )
        
        success_msg = f"✅ <b>Плейлист создан!</b>\n\n" \
                      f"📋 {playlist.name}\n" \
                      f"📝 {playlist.description or 'Без описания'}\n\n"
        
        # Если создание было инициировано для конкретного трека, добавляем его
        track_id = context.user_data.pop('plnew_track_id', None)
        if track_id:
            added = await db.add_track_to_playlist(playlist.id, track_id)
            if added:
                track = await db.get_track(track_id)
                track_name = track.name if track else "Трек"
                success_msg += f"✨ <b>{track_name}</b> добавлен в плейлист!"
        else:
            success_msg += "Теперь вы можете добавлять в него треки!"

        await update.message.reply_text(
            success_msg,
            parse_mode='HTML',
            reply_markup=KeyboardBuilder.back_button()
        )
        
        # Очищаем контекст
        context.user_data.pop('new_playlist_name', None)
        
        return ConversationHandler.END
    
    except Exception as e:
        await update.message.reply_text(
            f"❌ Ошибка при создании плейлиста: {str(e)}",
            parse_mode='HTML'
        )
        return ConversationHandler.END


async def cancel_playlist_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена создания плейлиста"""
    context.user_data.pop('new_playlist_name', None)
    
    await update.message.reply_text(
        "❌ Создание плейлиста отменено",
        reply_markup=KeyboardBuilder.main_menu()
    )
    return ConversationHandler.END


# ========== CALLBACK ОБРАБОТЧИКИ ==========

async def add_to_playlist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список плейлистов для добавления трека"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    track_id = query.data.replace('addto_', '')
    db = context.bot_data.get('db')
    
    if not db:
        return
    
    user = await db.get_or_create_user(user_id, update.effective_user)
    lang = user.language
    
    # Получаем плейлисты
    playlists = await db.get_user_playlists(user_id)
    
    message = "📂 <b>Выберите плейлист:</b>" if lang == "ru" else "📂 <b>Select a playlist:</b>"
    keyboard = KeyboardBuilder.playlist_selection(playlists, track_id, lang)
    
    await query.edit_message_reply_markup(reply_markup=keyboard)


async def select_playlist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить трек в выбранный плейлист"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.replace('pladd_', '').split('_')
    if len(data) < 2:
        return
    
    track_id = data[0]
    playlist_id = int(data[1])
    user_id = update.effective_user.id
    db = context.bot_data.get('db')
    
    if not db:
        return
    
    user = await db.get_or_create_user(user_id, update.effective_user)
    lang = user.language
    
    # Добавляем трек
    success = await db.add_track_to_playlist(playlist_id, track_id)
    
    if success:
        playlist = await db.get_playlist(playlist_id)
        msg = f"✅ Добавлено в «{playlist.name}»" if lang == "ru" else f"✅ Added to \"{playlist.name}\""
        await query.answer(msg, show_alert=True)
    else:
        msg = "⚠️ Трек уже есть в этом плейлисте" if lang == "ru" else "⚠️ Track already in this playlist"
        await query.answer(msg, show_alert=True)
    
    # Возвращаемся к основному меню действий
    keyboard = get_track_actions_keyboard(track_id)
    await query.edit_message_reply_markup(reply_markup=keyboard)


async def cancel_playlist_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена выбора плейлиста и возврат в меню действий"""
    query = update.callback_query
    await query.answer()
    
    track_id = query.data.replace('plcancel_', '')
    user_id = update.effective_user.id
    db = context.bot_data.get('db')
    
    # Возвращаемся к основному меню действий
    keyboard = get_track_actions_keyboard(track_id)
    await query.edit_message_reply_markup(reply_markup=keyboard)


async def create_playlist_for_track_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск процесса создания плейлиста из меню выбора (callback)"""
    query = update.callback_query
    await query.answer()
    
    track_id = query.data.replace('plnew_', '')
    context.user_data['plnew_track_id'] = track_id # Запоминаем, что после создания нужно добавить этот трек
    
    lang = "ru"
    db = context.bot_data.get('db')
    if db:
        user = await db.get_or_create_user(update.effective_user.id, update.effective_user)
        lang = user.language

    message = "📋 <b>Создание нового плейлиста</b>\n\nВведите название плейлиста (до 100 символов):" if lang == "ru" else \
              "📋 <b>Creating a new playlist</b>\n\nChoose a name for your playlist (up to 100 characters):"
    
    # Удаляем клавиатуру у сообщения с треком, чтобы не было путаницы
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except:
        pass

    # Отправляем НОВОЕ сообщение для ввода названия (т.к. нельзя редактировать текст аудио-сообщения)
    await query.message.reply_text(message, parse_mode='HTML')
    return WAITING_PLAYLIST_NAME
