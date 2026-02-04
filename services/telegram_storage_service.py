"""
Сервис для работы с Telegram Storage Channel
"""
import os
from typing import Optional, Dict
from telegram import Bot
from telegram.error import TelegramError
import config


class TelegramStorageService:
    """Сервис для загрузки и получения файлов из Telegram Storage Channel"""
    
    def __init__(self, bot: Bot, channel_id: str = None):
        self.bot = bot
        self.channel_id = channel_id or config.STORAGE_CHANNEL_ID
        print(f"📦 Telegram Storage initialized for channel: {self.channel_id}")
    
    async def upload_file(self, file_path: str, caption: str = None) -> Optional[Dict]:
        """
        Загрузить файл в Telegram Storage Channel
        
        Args:
            file_path: Путь к файлу
            caption: Описание файла (опционально)
            
        Returns:
            Dict с file_id и file_path или None при ошибке
        """
        try:
            if not os.path.exists(file_path):
                print(f"❌ File not found: {file_path}")
                return None
            
            file_size = os.path.getsize(file_path)
            print(f"📤 Uploading to Telegram Storage: {os.path.basename(file_path)} ({file_size / 1024 / 1024:.2f} MB)")
            
            # Отправляем файл в канал
            with open(file_path, 'rb') as audio_file:
                message = await self.bot.send_audio(
                    chat_id=self.channel_id,
                    audio=audio_file,
                    caption=caption,
                    read_timeout=60,
                    write_timeout=60
                )
            
            if message and message.audio:
                file_id = message.audio.file_id
                telegram_file_path = message.audio.file_unique_id
                
                print(f"✅ Uploaded to Telegram Storage: file_id={file_id[:20]}...")
                
                return {
                    'file_id': file_id,
                    'file_path': telegram_file_path,
                    'file_size': file_size,
                    'duration': message.audio.duration if message.audio.duration else 0
                }
            else:
                print("❌ Failed to upload file to Telegram")
                return None
                
        except TelegramError as e:
            print(f"❌ Telegram error while uploading: {e}")
            return None
        except Exception as e:
            print(f"❌ Error uploading to Telegram Storage: {e}")
            return None
    
    async def get_file_url(self, file_id: str) -> Optional[str]:
        """
        Получить прямую ссылку на файл из Telegram
        
        Args:
            file_id: ID файла в Telegram
            
        Returns:
            URL для скачивания или None при ошибке
        """
        try:
            file = await self.bot.get_file(file_id)
            if file and file.file_path:
                # Формируем прямую ссылку
                url = f"https://api.telegram.org/file/bot{config.TELEGRAM_BOT_TOKEN}/{file.file_path}"
                return url
            return None
        except TelegramError as e:
            print(f"❌ Telegram error while getting file URL: {e}")
            return None
        except Exception as e:
            print(f"❌ Error getting file URL: {e}")
            return None
    
    async def file_exists(self, file_id: str) -> bool:
        """
        Проверить, существует ли файл в Telegram
        
        Args:
            file_id: ID файла в Telegram
            
        Returns:
            True если файл существует, False иначе
        """
        try:
            file = await self.bot.get_file(file_id)
            return file is not None
        except:
            return False
