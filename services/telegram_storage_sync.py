
import asyncio
import httpx
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from database.db_manager import DatabaseManager

class DeepSyncService:
    """Сервис для глубокой синхронизации треков из Telegram Channel"""
    
    def __init__(self, storage_service, db_manager, download_service=None):
        self.storage = storage_service
        self.db = db_manager
        self.downloader = download_service
        self.base_url = storage_service.base_url
        self.channel_id = storage_service.channel_id
        
    async def run_deep_sync(self, range_size: int = 1000, start_id: Optional[int] = None):
        """
        Просканировать последние N сообщений в канале и добавить найденные аудио в БД
        """
        print(f"🕵️ Starting Deep Sync for last {range_size} messages...")
        
        # 1. Определяем начальный ID
        if not start_id:
            # Пытаемся получить последний ID через pinned message или отправив тестовое сообщение
            pinned = self.storage.get_pinned_message()
            if pinned:
                start_id = pinned.get('message_id', 0)
                print(f"📌 Starting from pinned message ID: {start_id}")
            else:
                # Отправляем и удаляем сообщение чтобы узнать текущий ID
                try:
                    resp = httpx.post(f"{self.base_url}/sendMessage", data={
                        'chat_id': self.channel_id,
                        'text': '🔍 Deep Sync Probe'
                    })
                    if resp.status_code == 200:
                        msg = resp.json().get('result', {})
                        start_id = msg.get('message_id', 0)
                        # Удаляем пробное сообщение
                        httpx.post(f"{self.base_url}/deleteMessage", data={
                            'chat_id': self.channel_id,
                            'message_id': start_id
                        })
                        print(f"🛰️ Current channel head ID: {start_id}")
                except:
                    start_id = 5000 # Fallback
        
        if not start_id:
            print("❌ Could not determine start ID for Deep Sync")
            return 0

        found_count = 0
        consecutive_errors = 0
        
        # Итерируемся назад
        for msg_id in range(start_id, max(0, start_id - range_size), -1):
            # Чтобы не спамить Telegram API, делаем небольшую паузу если нужно
            if msg_id % 20 == 0:
                await asyncio.sleep(0.5)
            
            try:
                # В Bot API нет getMessage, поэтому используем forwardMessage к самому боту
                # Это позволит получить объект Message с Audio без изменения канала
                # Мы используем chat_id бота (который совпадает с его токеном в начале?) 
                # Нет, нам нужен ID бота. Но мы можем форварднуть в тот же канал! 
                # Но это создаст дубликат.
                # Лучший способ - copyMessage в тот же канал с disable_notification=True и тут же удалить?
                # Или forwardMessage в приватный чат администратора (но мы не знаем его ID).
                
                # Попробуем getChat с конкретным message_id? Нет такого.
                
                # Используем трюк: forwardMessage в тот же канал, получаем результат, и ТУТ ЖЕ УДАЛЯЕМ.
                # Это на доли секунды появится в канале, но позволит извлечь данные.
                # UPD: Еще лучше - forwardMessage в какой-нибудь "мусорный" чат или просто Chat ID бота.
                # Если бот отправляет сообщение СЕБЕ, он знает свой ID из getMe.
                
                bot_info = httpx.get(f"{self.base_url}/getMe").json()
                bot_id = bot_info.get('result', {}).get('id')
                
                if not bot_id:
                    print("❌ Could not get bot ID")
                    break

                resp = httpx.post(f"{self.base_url}/forwardMessage", data={
                    'chat_id': bot_id,
                    'from_chat_id': self.channel_id,
                    'message_id': msg_id,
                    'disable_notification': True
                })
                
                if resp.status_code == 200:
                    msg_data = resp.json().get('result', {})
                    audio = msg_data.get('audio')
                    if audio:
                        file_id = audio.get('file_id')
                        caption = msg_data.get('caption', '')
                        
                        # Извлекаем артиста и название из капшена или аудио-метаданных
                        title = audio.get('title', 'Unknown')
                        artist = audio.get('performer', 'Unknown')
                        
                        # Если есть капшен вида "🎵 Artist - Title", используем его
                        if caption and " - " in caption:
                            clean_caption = caption.replace("🎵", "").strip()
                            parts = clean_caption.split(" - ", 1)
                            artist = parts[0].strip()
                            title = parts[1].strip()
                        
                        # Генерируем фейковый Track ID если его нет
                        track_id = audio.get('file_unique_id', f"sync_{msg_id}")
                        
                        # Пытаемся найти обложку на YouTube если есть загрузчик
                        image_url = None
                        if self.downloader:
                            metadata = await self.downloader.get_metadata_only(artist, title)
                            if metadata:
                                image_url = metadata.get('thumbnail')
                                print(f"🖼️ Found thumbnail for {artist} - {title}: {image_url[:40]}...")
                        
                        # Сохраняем в БД
                        print(f"✅ Found audio at {msg_id}: {artist} - {title}")
                        await self.db.save_telegram_file(
                            track_id=track_id,
                            file_id=file_id,
                            file_size=audio.get('file_size'),
                            artist=artist,
                            track_name=title,
                            image_url=image_url
                        )
                        found_count += 1
                        consecutive_errors = 0
                    else:
                        consecutive_errors = 0
                else:
                    consecutive_errors += 1
                    
                # Если слишком много ошибок подряд (сообщения не существуют), возможно мы дошли до начала
                if consecutive_errors > 50:
                    print(f"ℹ️ Reached end of history or too many missing messages at ID {msg_id}")
                    break
                    
            except Exception as e:
                print(f"⚠️ Error syncing message {msg_id}: {e}")
                consecutive_errors += 1
                
        print(f"🎉 Deep Sync complete! Found {found_count} tracks.")
        return found_count
