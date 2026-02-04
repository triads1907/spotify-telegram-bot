"""
Сервис для работы с Telegram Storage Channel
"""
import os
from typing import Optional, Dict
import httpx
import config


class TelegramStorageService:
    """Сервис для загрузки и получения файлов из Telegram Storage Channel"""
    
    def __init__(self, bot_token: str = None, channel_id: str = None):
        self.bot_token = bot_token or config.TELEGRAM_BOT_TOKEN
        self.channel_id = channel_id or config.STORAGE_CHANNEL_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        print(f"📦 Telegram Storage initialized for channel: {self.channel_id}")
    
    def upload_file(self, file_path: str, caption: str = None) -> Optional[Dict]:
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
            
            # Отправляем файл в канал через HTTP API
            with open(file_path, 'rb') as audio_file:
                files = {'audio': audio_file}
                data = {'chat_id': self.channel_id}
                if caption:
                    data['caption'] = caption
                
                response = httpx.post(
                    f"{self.base_url}/sendAudio",
                    files=files,
                    data=data,
                    timeout=120.0
                )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok') and result.get('result', {}).get('audio'):
                    audio = result['result']['audio']
                    file_id = audio['file_id']
                    telegram_file_path = audio.get('file_unique_id', '')
                    
                    print(f"✅ Uploaded to Telegram Storage: file_id={file_id[:20]}...")
                    
                    return {
                        'file_id': file_id,
                        'file_path': telegram_file_path,
                        'file_size': file_size,
                        'duration': audio.get('duration', 0)
                    }
            
            print(f"❌ Failed to upload file to Telegram: {response.text}")
            return None
                
        except Exception as e:
            print(f"❌ Error uploading to Telegram Storage: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_file_url(self, file_id: str) -> Optional[str]:
        """
        Получить прямую ссылку на файл из Telegram
        
        Args:
            file_id: ID файла в Telegram
            
        Returns:
            URL для скачивания или None при ошибке
        """
        try:
            response = httpx.get(
                f"{self.base_url}/getFile",
                params={'file_id': file_id},
                timeout=30.0
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok') and result.get('result', {}).get('file_path'):
                    file_path = result['result']['file_path']
                    url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
                    return url
            
            print(f"❌ Failed to get file URL: {response.text}")
            return None
            
        except Exception as e:
            print(f"❌ Error getting file URL: {e}")
            return None
    
    def file_exists(self, file_id: str) -> bool:
        """
        Проверить, существует ли файл в Telegram
        
        Args:
            file_id: ID файла в Telegram
            
        Returns:
            True если файл существует, False иначе
        """
        try:
            response = httpx.get(
                f"{self.base_url}/getFile",
                params={'file_id': file_id},
                timeout=30.0
            )
            return response.status_code == 200 and response.json().get('ok', False)
        except:
            return False
