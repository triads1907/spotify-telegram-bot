
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
        print(f"🕵️  [SYNC] Starting Deep Sync for last {range_size} messages...", flush=True)
        
        # 1. Получаем ID бота заранее
        try:
            bot_info = httpx.get(f"{self.base_url}/getMe", timeout=10.0).json()
            bot_id = bot_info.get('result', {}).get('id')
            if not bot_id:
                print("❌ [SYNC] Could not get bot ID from getMe", flush=True)
                return 0
        except Exception as e:
            print(f"❌ [SYNC] Failed to get bot info: {e}", flush=True)
            return 0

        # 2. Определяем начальный ID
        if not start_id:
            # Всегда используем probe message, так как pinned message это бэкап БД, а не музыка
            try:
                print(f"🛰️  [SYNC] Probing channel to find latest message ID...", flush=True)
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
                    print(f"🛰️  [SYNC] Current channel head ID: {start_id}", flush=True)
                else:
                    start_id = 5000  # Fallback
            except Exception as e:
                print(f"⚠️  [SYNC] Probe failed: {e}. Using fallback.", flush=True)
                start_id = 5000
        
        if not start_id:
            print("❌ [SYNC] Could not determine start ID", flush=True)
            return 0

        found_count = 0
        consecutive_errors = 0
        
        # Итерируемся назад
        print(f"🔎 [SYNC] Scanning IDs from {start_id} down to {max(0, start_id - range_size)}...", flush=True)
        
        for msg_id in range(start_id, max(0, start_id - range_size), -1):
            if msg_id % 50 == 0:
                await asyncio.sleep(0.5)
            
            try:
                # Используем Self-Forward: форвардим в тот же канал для получения метаданных
                # Это обходит ограничение "bots can't send messages to bots"
                resp = httpx.post(f"{self.base_url}/forwardMessage", data={
                    'chat_id': self.channel_id,
                    'from_chat_id': self.channel_id,
                    'message_id': msg_id,
                    'disable_notification': True
                }, timeout=10.0)
                
                if resp.status_code == 200:
                    msg_data = resp.json().get('result', {})
                    new_msg_id = msg_data.get('message_id')
                    
                    audio = msg_data.get('audio')
                    if audio:
                        file_id = audio.get('file_id')
                        caption = msg_data.get('caption', '')
                        title = audio.get('title', 'Unknown')
                        artist = audio.get('performer', 'Unknown')
                        
                        if caption and " - " in caption:
                            clean_caption = caption.replace("🎵", "").strip()
                            if " - " in clean_caption:
                                parts = clean_caption.split(" - ", 1)
                                artist = parts[0].strip()
                                title = parts[1].strip()
                        
                        track_id = audio.get('file_unique_id', f"sync_{msg_id}")
                        
                        image_url = None
                        if self.downloader:
                            metadata = await self.downloader.get_metadata_only(artist, title)
                            if metadata:
                                image_url = metadata.get('thumbnail')
                        
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
                        print(f"✅ [SYNC] Recovered: {artist} - {title}", flush=True)
                    else:
                        consecutive_errors = 0
                        if msg_id % 100 == 0:
                            print(f"ℹ️  [SYNC] ID {msg_id} is not audio. Continuing...", flush=True)

                    # Сразу удаляем временный дубликат
                    if new_msg_id:
                        httpx.post(f"{self.base_url}/deleteMessage", data={
                            'chat_id': self.channel_id,
                            'message_id': new_msg_id
                        })
                elif resp.status_code == 400:
                    consecutive_errors += 1
                else:
                    consecutive_errors += 1
                    
                if consecutive_errors > 200:
                    print(f"ℹ️  [SYNC] Reached sparse history at ID {msg_id}. Stopping.", flush=True)
                    break
                    
            except Exception as e:
                consecutive_errors += 1
                if msg_id % 100 == 0:
                    print(f"⚠️  [SYNC] Error ID {msg_id}: {e}", flush=True)
                
        print(f"🎉 [SYNC] Deep Sync complete! Found {found_count} tracks.", flush=True)
        return found_count
