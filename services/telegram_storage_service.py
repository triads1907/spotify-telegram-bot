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
                    message = result['result']
                    document = message['document']
                    file_id = document['file_id']
                    file_name = document.get('file_name', '')
                    message_id = message.get('message_id')
                    
                    print(f"✅ Uploaded document to Telegram: {file_name}, message_id={message_id}")
                    
                    return {
                        'file_id': file_id,
                        'file_name': file_name,
                        'file_size': file_size,
                        'message_id': message_id
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

    def pin_message(self, message_id: int) -> bool:
        """Закрепить сообщение в канале"""
        try:
            response = httpx.post(
                f"{self.base_url}/pinChatMessage",
                data={
                    'chat_id': self.channel_id,
                    'message_id': message_id,
                    'disable_notification': True
                },
                timeout=30.0
            )
            return response.status_code == 200 and response.json().get('ok', False)
        except Exception as e:
            print(f"❌ Error pinning message: {e}")
            return False

    def get_pinned_message(self) -> Optional[Dict]:
        """Получить закрепленное сообщение в канале"""
        try:
            response = httpx.get(
                f"{self.base_url}/getChat",
                params={'chat_id': self.channel_id},
                timeout=30.0
            )
            if response.status_code == 200:
                result = response.json()
                if result.get('ok') and result.get('result', {}).get('pinned_message'):
                    return result['result']['pinned_message']
            return None
        except Exception as e:
            print(f"❌ Error getting pinned message: {e}")
            return None
    async def sync_channel_files(self, db_manager) -> Dict:
        """
        Синхронизировать все аудиофайлы из канала в базу данных
        
        Args:
            db_manager: Экземпляр DatabaseManager
            
        Returns:
            Dict со статистикой синхронизации
        """
        print(f"🔄 Starting library synchronization from channel {self.channel_id}...")
        
        # 1. Получаем текущий максимальный ID сообщения
        try:
            temp_msg_resp = httpx.post(
                f"{self.base_url}/sendMessage",
                data={'chat_id': self.channel_id, 'text': '🔄 Syncing library...'},
                timeout=30.0
            )
            temp_msg = temp_msg_resp.json()
            
            if not temp_msg.get('ok'):
                print(f"❌ Could not initiate sync: {temp_msg.get('description')}")
                return {'error': f"Could not initiate sync: {temp_msg.get('description')}", 'added': 0}
                
            max_id = temp_msg['result']['message_id']
            # Удаляем временное сообщение
            httpx.post(
                f"{self.base_url}/deleteMessage",
                data={'chat_id': self.channel_id, 'message_id': max_id}
            )
        except Exception as e:
            print(f"❌ Sync error (max_id): {e}")
            return {'error': str(e), 'added': 0}

        added_count = 0
        skipped_count = 0
        error_count = 0
        consecutive_empty = 0
        
        # 2. Сканируем сообщения вниз (последние 300 сообщений для надежности)
        print(f"🕵️ Scanning messages from ID {max_id-1} downwards...")
        
        for msg_id in range(max_id - 1, max(0, max_id - 300), -1):
            if consecutive_empty > 30: # Если 30 сообщений подряд не аудио - скорее всего всё
                print(f"ℹ️ Stop scanning at ID {msg_id} (30 consecutive empty messages)")
                break
                
            try:
                # Пытаемся переслать сообщение самому себе в тот же канал для получения содержимого
                # Это стандартный способ получить данные сообщения по ID в Bot API
                response = httpx.post(
                    f"{self.base_url}/forwardMessage",
                    data={
                        'chat_id': self.channel_id,
                        'from_chat_id': self.channel_id,
                        'message_id': msg_id,
                        'disable_notification': True
                    },
                    timeout=15.0
                ).json()
                
                if not response.get('ok'):
                    consecutive_empty += 1
                    continue
                
                # Получили данные
                msg_data = response['result']
                # Удаляем пересланное сообщение сразу
                httpx.post(
                    f"{self.base_url}/deleteMessage",
                    data={'chat_id': self.channel_id, 'message_id': msg_data['message_id']}
                )
                
                # Проверяем наличие аудио или документа (часто аудио загружают как документ)
                audio_data = None
                if 'audio' in msg_data:
                    audio_data = msg_data['audio']
                elif 'document' in msg_data and msg_data['document'].get('mime_type', '').startswith('audio/'):
                    audio_data = msg_data['document']
                
                if audio_data:
                    caption = msg_data.get('caption', '')
                    file_id = audio_data['file_id']
                    file_unique_id = audio_data.get('file_unique_id', f"tg_{msg_id}")
                    
                    # Парсим информацию
                    artist = audio_data.get('performer', 'Unknown Artist')
                    title = audio_data.get('title', audio_data.get('file_name', 'Unknown Track'))
                    
                    if caption and ' - ' in caption:
                        parts = caption.split(' - ', 1)
                        artist = parts[0].strip()
                        title = parts[1].strip()
                    
                    # Генерируем track_id на основе file_unique_id
                    track_id = f"tg_{file_unique_id}"
                    
                    # Проверяем не существует ли уже
                    existing = await db_manager.get_track(track_id)
                    if not existing:
                        track_info = {
                            'id': track_id,
                            'name': title,
                            'artist': artist,
                            'spotify_url': f"https://t.me/c/{str(self.channel_id).replace('-100', '')}/{msg_id}",
                            'image_url': None,
                            'duration_ms': audio_data.get('duration', 0) * 1000 if 'duration' in audio_data else 0
                        }
                        await db_manager.get_or_create_track(track_info)
                        await db_manager.update_track_cache(track_id, file_id)
                        added_count += 1
                        print(f"➕ Added track: {artist} - {title}")
                        consecutive_empty = 0
                    else:
                        skipped_count += 1
                        consecutive_empty = 0
                else:
                    consecutive_empty += 1
                    
            except Exception as e:
                print(f"⚠️ Error syncing message {msg_id}: {e}")
                error_count += 1
                consecutive_empty += 1
                
        print(f"🏁 Sync finished! Added: {added_count}, Skipped: {skipped_count}, Errors: {error_count}")
        return {'added': added_count, 'skipped': skipped_count, 'errors': error_count}
