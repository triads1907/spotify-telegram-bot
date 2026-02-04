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
    
    def upload_document(self, file_path: str, caption: str = None) -> Optional[Dict]:
        """
        Загрузить документ (например, БД файл) в Telegram Storage Channel
        
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
            print(f"📤 Uploading document to Telegram: {os.path.basename(file_path)} ({file_size / 1024:.2f} KB)")
            
            # Отправляем файл как document в канал через HTTP API
            with open(file_path, 'rb') as doc_file:
                files = {'document': doc_file}
                data = {'chat_id': self.channel_id}
                if caption:
                    data['caption'] = caption
                
                response = httpx.post(
                    f"{self.base_url}/sendDocument",
                    files=files,
                    data=data,
                    timeout=120.0
                )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok') and result.get('result', {}).get('document'):
                    document = result['result']['document']
                    file_id = document['file_id']
                    file_name = document.get('file_name', '')
                    
                    print(f"✅ Uploaded document to Telegram: {file_name}")
                    
                    return {
                        'file_id': file_id,
                        'file_name': file_name,
                        'file_size': file_size
                    }
            
            print(f"❌ Failed to upload document to Telegram: {response.text}")
            return None
                
        except Exception as e:
            print(f"❌ Error uploading document to Telegram: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def download_file(self, file_id: str, save_path: str) -> bool:
        """
        Скачать файл из Telegram и сохранить локально
        
        Args:
            file_id: ID файла в Telegram
            save_path: Путь для сохранения файла
            
        Returns:
            True если файл успешно скачан
        """
        try:
            # Получаем информацию о файле
            file_url = self.get_file_url(file_id)
            
            if not file_url:
                print("❌ Failed to get file URL")
                return False
            
            print(f"📥 Downloading file from Telegram...")
            
            # Скачиваем файл
            response = httpx.get(file_url, timeout=120.0)
            
            if response.status_code == 200:
                # Сохраняем файл
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                
                print(f"✅ File downloaded: {save_path} ({len(response.content) / 1024:.2f} KB)")
                return True
            else:
                print(f"❌ Failed to download file: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Error downloading file: {e}")
            import traceback
            traceback.print_exc()
            return False
