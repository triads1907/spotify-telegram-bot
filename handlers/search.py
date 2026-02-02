"""
Обработчики поиска и обработки Spotify ссылок
АВТОМАТИЧЕСКОЕ скачивание при получении ссылки
"""
import os
import hashlib
from telegram import Update
from telegram.ext import ContextTypes
from services.spotify_service import SpotifyService
from services.download_service import DownloadService
from services.message_builder import MessageBuilder
from utils.strings import get_string
from utils.keyboards import (
    get_search_results_keyboard, 
    get_track_actions_keyboard,
    KeyboardBuilder
)


async def handle_spotify_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик Spotify ссылок
    АВТОМАТИЧЕСКИ парсит ссылку и скачивает трек
    """
    message_text = update.message.text
    spotify_service: SpotifyService = context.bot_data.get('spotify')
    download_service: DownloadService = context.bot_data.get('download_service')
    db = context.bot_data.get('db')
    
    # Получаем язык пользователя сразу (Функция 19)
    user_id = update.effective_user.id
    lang = "ru"
    if db:
        user = await db.get_or_create_user(user_id, update.effective_user)
        lang = user.language
    
    # Парсим URL
    parsed = spotify_service.parse_spotify_url(message_text)
    
    if not parsed:
        await update.message.reply_text(
            "❌ Link not recognized." if lang == "en" else "❌ Не удалось распознать ссылку Spotify.",
            parse_mode='HTML'
        )
        return
    
    if parsed['type'] != 'track':
        await update.message.reply_text(
            "⚠️ Only tracks are supported for now." if lang == "en" else "⚠️ Пока поддерживаются только треки.\nОтправьте ссылку на отдельный трек.",
            parse_mode='HTML'
        )
        return
    
    # Получаем настройки из модели пользователя (Функция 3, 18)
    user = await db.get_or_create_user(user_id, update.effective_user)
    quality = user.preferred_quality
    file_format = user.format
    lang = user.language
    
    # Шаг 1: Получаем информацию о треке
    status_msg = await update.message.reply_text(get_string("searching", lang))
    
    try:
        track_info = spotify_service.get_track_info_from_url(message_text)
        
        if not track_info:
            await status_msg.edit_text("❌ Не удалось получить информацию о треке")
            return
        
        # Генерируем ID для трека
        track_id = hashlib.md5(message_text.encode()).hexdigest()[:16]
        track_info['id'] = track_id
        
        # Сохраняем в БД
        if db:
            await db.get_or_create_track(track_info)
        
        # Проверяем кэш (Функция 10)
        cached_file_id = None
        if db:
            cached_file_id = await db.get_cached_file_id(track_id, file_format=file_format, quality=quality)
        
        if cached_file_id:
            # Файл уже есть в кэше, отправляем сразу
            await status_msg.edit_text(get_string("from_cache", lang))
            try:
                # Формируем информативный caption для кэша
                if file_format == 'mp3':
                    quality_display = f"{quality} kbps"
                else:
                    if quality == '1411': quality_display = "1411 kbps (CD)"
                    elif quality == '2300': quality_display = "2300 kbps (48kHz/24bit)"
                    elif quality == '4600': quality_display = "4600 kbps (96kHz/24bit)"
                    elif quality == '9200': quality_display = "9200 kbps (192kHz/24bit)"
                    else: quality_display = "Lossless"
                format_label = file_format.upper()
                caption = f"🎵 <b>{track_info['name']}</b>\n👤 {track_info['artist']}\n\n" + \
                          f"🎧 {format_label} • {quality_display}\n" + \
                          (f"✨ From cache" if lang == "en" else f"✨ Из кэша")
                
                keyboard = get_track_actions_keyboard(track_id)
                
                keyboard = get_track_actions_keyboard(track_id)
                
                # Скачиваем обложку для thumbnail если есть
                thumb_path = None
                if track_info.get('image_url'):
                    thumb_path = await download_service.download_image(track_info['image_url'])
                
                thumb_file = None
                if thumb_path and os.path.exists(thumb_path):
                    thumb_file = open(thumb_path, 'rb')

                try:
                    await update.message.reply_audio(
                        audio=cached_file_id,
                        title=track_info['name'],
                        performer=track_info['artist'],
                        caption=caption,
                        thumbnail=thumb_file,
                        parse_mode='HTML',
                        reply_markup=keyboard,
                        read_timeout=600,
                        write_timeout=600
                    )
                finally:
                    if thumb_file:
                        thumb_file.close()
                
                # Отдельное сообщение с клавиатурой
                action_msg = "📝 <b>Действия с треком:</b>" if lang == "ru" else "📝 <b>Track actions:</b>"
                await update.message.reply_text(action_msg, reply_markup=keyboard, parse_mode='HTML')
                
                await status_msg.delete()
                # Записываем в историю
                if db:
                    history_quality = f"{quality} kbps" if file_format == 'mp3' else f"Hi-Res FLAC ({quality} kbps)"
                    await db.add_download_to_history(user_id, track_id, history_quality, 0)
                
                return
            except Exception as e:
                print(f"❌ Ошибка отправки из кэша: {e}")
                # Продолжаем обычное скачивание
        
        # Шаг 2: Показываем информацию
        message_key = "downloading"
        info_message = get_string(message_key, lang, name=track_info['name'], artist=track_info['artist'])
        
        await status_msg.edit_text(info_message.strip(), parse_mode='HTML')
        
        # Шаг 3: АВТОМАТИЧЕСКИ скачиваем
        if not download_service:
            await status_msg.edit_text(
                f"❌ Сервис скачивания недоступен\n\n"
                f"🎵 {track_info['name']}\n\n"
                f"🔗 <a href=\"{track_info['spotify_url']}\">Открыть в Spotify</a>",
                parse_mode='HTML'
            )
            return
        
        # Скачиваем трек используя только название
        # YouTube сам найдёт правильного исполнителя
        search_query = track_info['name']
        if track_info.get('artist'):
            search_query = f"{track_info['artist']} {track_info['name']}"
        
        # Скачиваем с выбранным качеством и форматом (Функция 3, 18)
        result = await download_service.search_and_download_by_query(
            search_query, 
            quality=quality, 
            file_format=file_format
        )

        
        if not result or not result.get('file_path'):
            await status_msg.edit_text(
                f"❌ Не удалось скачать трек с YouTube\n\n"
                f"🎵 {track_info['name']}\n"
                f"👤 {track_info['artist']}\n\n"
                f"Попробуйте другой трек или откройте в Spotify:\n"
                f"{track_info['spotify_url']}",
                parse_mode='HTML'
            )
            return
        
        # Проверяем размер файла (Лимит Telegram Bot API - 50 MB)
        file_size_mb = result.get('file_size', 0) / (1024 * 1024)
        if file_size_mb > 50:
            await status_msg.edit_text(
                get_string("error_file_too_large", lang, size=f"{file_size_mb:.1f}"),
                parse_mode='HTML'
            )
            return

        # Шаг 4: Отправляем файл
        await status_msg.edit_text(
            get_string("uploading", lang) + f"\n\n🎵 <b>{track_info['name']}</b>",
            parse_mode='HTML'
        )
        
        # Проверяем существование файла
        if not os.path.exists(result['file_path']):
            await status_msg.edit_text(
                f"❌ Файл не найден после скачивания\n\n"
                f"🎵 {track_info['name']}\n\n"
                f"Попробуйте другой трек или откройте в Spotify:\n"
                f"{track_info['spotify_url']}",
                parse_mode='HTML'
            )
            return
        
        try:
            with open(result['file_path'], 'rb') as audio_file:
                # Формируем caption с качеством и форматом
                if file_format == 'mp3':
                    quality_display = f"{quality} kbps"
                else:
                    if quality == '1411': quality_display = "1411 kbps (CD)"
                    elif quality == '4600': quality_display = "4600 kbps (Hi-Res)"
                    elif quality == '9200': quality_display = "9200 kbps (Ultra Hi-Res)"
                    else: quality_display = "Lossless"
                format_label = file_format.upper()
                caption = f"🎵 <b>{track_info['name']}</b>\n👤 {track_info['artist']}\n\n" + \
                          f"🎧 {format_label} • {quality_display}"
                
                # Проверяем, в избранном ли трек
                is_fav = await db.is_favorite(user_id, track_id) if db else False
                keyboard = get_track_actions_keyboard(track_id)
                
                keyboard = get_track_actions_keyboard(track_id)
                
                # Скачиваем обложку для thumbnail если есть
                thumb_path = None
                if track_info.get('image_url'):
                    thumb_path = await download_service.download_image(track_info['image_url'])
                
                thumb_file = None
                if thumb_path and os.path.exists(thumb_path):
                    thumb_file = open(thumb_path, 'rb')

                try:
                    sent_message = await update.message.reply_audio(
                        audio=audio_file,
                        title=track_info['name'],
                        performer=track_info['artist'],
                        caption=caption,
                        thumbnail=thumb_file,
                        parse_mode='HTML',
                        reply_markup=keyboard,
                        read_timeout=600,
                        write_timeout=600
                    )
                finally:
                    if thumb_file:
                        thumb_file.close()
                
                # Сохраняем file_id в кэш (Функция 10)
                if db and sent_message.audio:
                    await db.update_track_cache(
                        track_id, 
                        sent_message.audio.file_id,
                        file_format=file_format,
                        quality=quality
                    )
                
                # Записываем в историю (Функция 5)
                if db:
                    file_size = result.get('file_size', 0)
                    history_quality = f"{quality} kbps" if file_format == 'mp3' else f"Hi-Res FLAC ({quality} kbps)"
                    await db.add_download_to_history(user_id, track_id, history_quality, file_size)
            
            # Удаляем статусное сообщение
            await status_msg.delete()
            
            # Удаляем временный файл
            download_service.cleanup_file(result['file_path'])
            
        except Exception as e:
            await status_msg.edit_text(
                f"❌ Ошибка при отправке файла: {str(e)}\n\n"
                f"🎵 {track_info['name']}",
                parse_mode='HTML'
            )
            print(f"❌ Ошибка отправки файла: {e}")

    
    except Exception as e:
        await status_msg.edit_text(
            f"❌ Ошибка при обработке: {str(e)}\n\n"
            f"Попробуйте другую ссылку.",
            parse_mode='HTML'
        )
        print(f"❌ Ошибка в handle_spotify_link: {e}")


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /search"""
    user_id = update.effective_user.id
    db = context.bot_data.get('db')
    lang = "ru"
    if db:
        user = await db.get_or_create_user(user_id, update.effective_user)
        lang = user.language
        
    await update.message.reply_text(
        get_string("search_welcome", lang),
        parse_mode='HTML'
    )
