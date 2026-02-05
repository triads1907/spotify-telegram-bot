"""
Database Backup Service - ╨░╨▓╤В╨╛╨╝╨░╤В╨╕╤З╨╡╤Б╨║╨╕╨╣ backup ╨╕ ╨▓╨╛╤Б╤Б╤В╨░╨╜╨╛╨▓╨╗╨╡╨╜╨╕╨╡ ╨С╨Ф ╤З╨╡╤А╨╡╨╖ Telegram
"""
import os
import asyncio
import shutil
from datetime import datetime
from typing import Optional
import httpx


class DatabaseBackupService:
    """╨б╨╡╤А╨▓╨╕╤Б ╨┤╨╗╤П backup ╨╕ ╨▓╨╛╤Б╤Б╤В╨░╨╜╨╛╨▓╨╗╨╡╨╜╨╕╤П ╨С╨Ф ╤З╨╡╤А╨╡╨╖ Telegram Storage"""
    
    def __init__(self, storage_service, db_path: str):
        """
        Args:
            storage_service: TelegramStorageService instance
            db_path: ╨Я╤Г╤В╤М ╨║ ╤Д╨░╨╣╨╗╤Г ╨С╨Ф (╨╜╨░╨┐╤А╨╕╨╝╨╡╤А, 'spotify_bot.db')
        """
        self.storage = storage_service
        self.db_path = db_path
        self.backup_file_id = None
        self.is_running = False
        
        print(f"ЁЯУж Database Backup Service initialized for: {db_path}")
    
    async def restore_from_telegram(self) -> bool:
        """
        ╨Т╨╛╤Б╤Б╤В╨░╨╜╨╛╨▓╨╕╤В╤М ╨С╨Ф ╨╕╨╖ Telegram ╨┐╤А╨╕ ╤Б╤В╨░╤А╤В╨╡ ╨┐╤А╨╕╨╗╨╛╨╢╨╡╨╜╨╕╤П
        
        Returns:
            True ╨╡╤Б╨╗╨╕ ╨С╨Ф ╤Г╤Б╨┐╨╡╤И╨╜╨╛ ╨▓╨╛╤Б╤Б╤В╨░╨╜╨╛╨▓╨╗╨╡╨╜╨░, False ╨╡╤Б╨╗╨╕ backup ╨╜╨╡ ╨╜╨░╨╣╨┤╨╡╨╜
        """
        try:
            print("ЁЯФН Checking for latest backup in Telegram pinned message...")
            backup_info = await self._find_latest_backup()
            
            if not backup_info:
                print("тД╣я╕П  No backup found in Telegram, using local database (if exists)")
                return False
            
            # ╨Х╤Б╨╗╨╕ ╨╗╨╛╨║╨░╨╗╤М╨╜╤Л╨╣ ╤Д╨░╨╣╨╗ ╤Б╤Г╤Й╨╡╤Б╤В╨▓╤Г╨╡╤В, ╨┐╤А╨╛╨▓╨╡╤А╨╕╨╝, ╨╜╤Г╨╢╨╜╨╛ ╨╗╨╕ ╨╡╨│╨╛ ╨╖╨░╨╝╨╡╨╜╤П╤В╤М
            if os.path.exists(self.db_path):
                file_size = os.path.getsize(self.db_path)
                # ╨Х╤Б╨╗╨╕ ╤Д╨░╨╣╨╗ ╨┐╨╛╨┤╨╛╨╖╤А╨╕╤В╨╡╨╗╤М╨╜╨╛ ╨╝╨░╨╗╨╡╨╜╤М╨║╨╕╨╣ (╤Б╨▓╨╡╨╢╨╡╤Б╨╛╨╖╨┤╨░╨╜╨╜╤Л╨╣) - ╨╖╨░╨╝╨╡╨╜╤П╨╡╨╝ ╨▒╨╡╨╖ ╨▓╨╛╨┐╤А╨╛╤Б╨╛╨▓
                if file_size < 32768: # 32KB - ╤Н╤В╨╛ ╨┐╤А╨╕╨╝╨╡╤А╨╜╨╛ ╨┐╤Г╤Б╤В╨░╤П ╨С╨Ф ╤Б╨╛ ╤Б╤Е╨╡╨╝╨╛╨╣
                    print(f"тЪая╕П  Local database is too small ({file_size} bytes), overwriting with backup...")
                else:
                    print(f"тЬЕ Local database exists and looks healthy ({file_size} bytes). Skipping restoration.")
                    return False
            
            # ╨б╨║╨░╤З╨╕╨▓╨░╨╡╨╝ backup
            print(f"ЁЯУе Downloading database backup from Telegram...")
            success = await self._download_backup(backup_info['file_id'])
            
            if success:
                print("тЬЕ Database successfully restored from Telegram!")
                self.backup_file_id = backup_info['file_id']
                return True
            else:
                print("тЭМ Failed to restore database from Telegram")
                return False
                
        except Exception as e:
            print(f"тЭМ Error restoring database: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def backup_to_telegram(self) -> bool:
        """
        ╨б╨╛╨╖╨┤╨░╤В╤М backup ╨С╨Ф ╨▓ Telegram
        
        Returns:
            True ╨╡╤Б╨╗╨╕ backup ╤Г╤Б╨┐╨╡╤И╨╜╨╛ ╤Б╨╛╨╖╨┤╨░╨╜
        """
        try:
            if not os.path.exists(self.db_path):
                print(f"тЪая╕П  Database file not found: {self.db_path}")
                return False
            
            file_size = os.path.getsize(self.db_path)
            print(f"ЁЯТ╛ Creating database backup ({file_size / 1024:.2f} KB)...")
            
            # ╨Ч╨░╨│╤А╤Г╨╢╨░╨╡╨╝ ╨С╨Ф ╨║╨░╨║ document ╨▓ Telegram
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            caption = f"ЁЯЧДя╕П Database Backup - {timestamp}"
            
            result = self.storage.upload_document(self.db_path, caption)
            
            if result and result.get('file_id'):
                self.backup_file_id = result['file_id']
                print(f"тЬЕ Database backup created: {result['file_id'][:20]}...")
                
                # ╨Ч╨░╨║╤А╨╡╨┐╨╗╤П╨╡╨╝ ╤Б╨╛╨╛╨▒╤Й╨╡╨╜╨╕╨╡, ╤З╤В╨╛╨▒╤Л ╨▒╨╛╤В ╨▓╤Б╨╡╨│╨┤╨░ ╨╝╨╛╨│ ╨╡╨│╨╛ ╨╜╨░╨╣╤В╨╕
                if result.get('message_id'):
                    pin_success = self.storage.pin_message(result['message_id'])
                    if pin_success:
                        print(f"ЁЯУМ Backup message pinned: {result['message_id']}")
                
                # Cleanup old backups (keep only last 2)
                await self.cleanup_old_backups(keep_count=2)
                
                return True
            else:
                print("тЭМ Failed to create database backup")
                return False
                
        except Exception as e:
            print(f"тЭМ Error creating backup: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def start_periodic_backup(self, interval: int = 300):
        """
        ╨Ч╨░╨┐╤Г╤Б╤В╨╕╤В╤М ╨┐╨╡╤А╨╕╨╛╨┤╨╕╤З╨╡╤Б╨║╨╕╨╣ backup ╨С╨Ф
        
        Args:
            interval: ╨Ш╨╜╤В╨╡╤А╨▓╨░╨╗ ╨▓ ╤Б╨╡╨║╤Г╨╜╨┤╨░╤Е (╨┐╨╛ ╤Г╨╝╨╛╨╗╤З╨░╨╜╨╕╤О 300 = 5 ╨╝╨╕╨╜╤Г╤В)
        """
        self.is_running = True
        print(f"тП░ Starting periodic database backup (every {interval} seconds)...")
        
        while self.is_running:
            try:
                await asyncio.sleep(interval)
                
                if self.is_running:
                    await self.backup_to_telegram()
                    
            except asyncio.CancelledError:
                print("ЁЯЫС Periodic backup cancelled")
                break
            except Exception as e:
                print(f"тЭМ Error in periodic backup: {e}")
                # ╨Я╤А╨╛╨┤╨╛╨╗╨╢╨░╨╡╨╝ ╤А╨░╨▒╨╛╤В╤Г ╨┤╨░╨╢╨╡ ╨┐╤А╨╕ ╨╛╤И╨╕╨▒╨║╨╡
                continue
    
    def stop_periodic_backup(self):
        """╨Ю╤Б╤В╨░╨╜╨╛╨▓╨╕╤В╤М ╨┐╨╡╤А╨╕╨╛╨┤╨╕╤З╨╡╤Б╨║╨╕╨╣ backup"""
        print("ЁЯЫС Stopping periodic database backup...")
        self.is_running = False
    
    async def _find_latest_backup(self) -> Optional[dict]:
        """
        ╨Э╨░╨╣╤В╨╕ ╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╕╨╣ backup ╨С╨Ф ╨▓ Telegram ╨║╨░╨╜╨░╨╗╨╡
        
        Returns:
            Dict ╤Б ╨╕╨╜╤Д╨╛╤А╨╝╨░╤Ж╨╕╨╡╨╣ ╨╛ backup ╨╕╨╗╨╕ None
        """
        try:
            # ╨Я╨╛╨╗╤Г╤З╨░╨╡╨╝ ╨╖╨░╨║╤А╨╡╨┐╨╗╨╡╨╜╨╜╨╛╨╡ ╤Б╨╛╨╛╨▒╤Й╨╡╨╜╨╕╨╡ ╨╕╨╖ ╨║╨░╨╜╨░╨╗╨░
            message = self.storage.get_pinned_message()
            
            if not message or not message.get('document'):
                # ╨Х╤Б╨╗╨╕ ╨╖╨░╨║╤А╨╡╨┐╨╗╨╡╨╜╨╜╨╛╨│╨╛ ╤Б╨╛╨╛╨▒╤Й╨╡╨╜╨╕╤П ╨╜╨╡╤В, ╨┐╨╛╨┐╤А╨╛╨▒╤Г╨╡╨╝ ╨┐╨╛╨╕╤Б╨║╨░╤В╤М ╨▓ ╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╕╤Е ╤Б╨╛╨╛╨▒╤Й╨╡╨╜╨╕╤П╤Е (╨╜╨╛ ╤Н╤В╨╛ ╨╝╨╡╨╜╨╡╨╡ ╨╜╨░╨┤╨╡╨╢╨╜╨╛)
                print("тД╣я╕П  No pinned message found in channel")
                return None
            
            doc = message['document']
            # ╨Я╤А╨╛╨▓╨╡╤А╤П╨╡╨╝, ╤З╤В╨╛ ╤Н╤В╨╛ ╤Д╨░╨╣╨╗ ╨С╨Ф
            if doc.get('file_name', '').endswith('.db'):
                print(f"тЬЕ Found backup in pinned message: {doc.get('file_name')}")
                return {
                    'file_id': doc['file_id'],
                    'file_name': doc.get('file_name'),
                    'file_size': doc.get('file_size'),
                    'date': message.get('date')
                }
            
            return None
            
        except Exception as e:
            print(f"тЭМ Error finding backup: {e}")
            return None
    
    async def _download_backup(self, file_id: str) -> bool:
        """
        ╨б╨║╨░╤З╨░╤В╤М backup ╨╕╨╖ Telegram
        
        Args:
            file_id: ID ╤Д╨░╨╣╨╗╨░ ╨▓ Telegram
            
        Returns:
            True ╨╡╤Б╨╗╨╕ ╤Г╤Б╨┐╨╡╤И╨╜╨╛ ╤Б╨║╨░╤З╨░╨╜
        """
        try:
            # ╨б╨╛╨╖╨┤╨░╨╡╨╝ ╨▓╤А╨╡╨╝╨╡╨╜╨╜╤Л╨╣ ╤Д╨░╨╣╨╗ ╨┤╨╗╤П backup
            temp_path = f"{self.db_path}.backup"
            
            # ╨б╨║╨░╤З╨╕╨▓╨░╨╡╨╝ ╤Д╨░╨╣╨╗
            success = self.storage.download_file(file_id, temp_path)
            
            if success and os.path.exists(temp_path):
                # ╨Ч╨░╨╝╨╡╨╜╤П╨╡╨╝ ╤В╨╡╨║╤Г╤Й╤Г╤О ╨С╨Ф ╨╜╨░ backup
                if os.path.exists(self.db_path):
                    os.remove(self.db_path)
                
                # ╨б╨╛╨╖╨┤╨░╨╡╨╝ ╨┤╨╕╤А╨╡╨║╤В╨╛╤А╨╕╤О ╨╡╤Б╨╗╨╕ ╨╡╤С ╨╜╨╡╤В
                os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
                
                shutil.move(temp_path, self.db_path)
                
                # ╨п╨▓╨╜╨╛ ╤Г╤Б╤В╨░╨╜╨░╨▓╨╗╨╕╨▓╨░╨╡╨╝ ╨┐╤А╨░╨▓╨░ ╨╜╨░ ╨╖╨░╨┐╨╕╤Б╤М (chmod 666)
                try:
                    os.chmod(self.db_path, 0o666)
                except Exception as chmod_e:
                    print(f"тЪая╕П  Warning: Could not set permissions: {chmod_e}")
                
                print(f"тЬЕ Database file restored and permissions set: {self.db_path}")
                return True
            else:
                print("тЭМ Failed to download backup file")
                return False
                
        except Exception as e:
            print(f"тЭМ Error downloading backup: {e}")
            return False
    
    async def cleanup_old_backups(self, keep_count: int = 2):
        """
        Удалить старые бэкапы БД, оставив только последние keep_count
        
        Args:
            keep_count: Количество последних бэкапов для сохранения (по умолчанию 2)
        """
        try:
            print(f"🧹 Cleaning up old backups (keeping last {keep_count})...")
            
            # Получаем закрепленное сообщение (последний бэкап)
            pinned = self.storage.get_pinned_message()
            if not pinned or not pinned.get('document'):
                print("ℹ️  No pinned backup found, skipping cleanup")
                return
            
            current_message_id = pinned.get('message_id')
            if not current_message_id:
                return
            
            # Пробуем удалить предыдущие сообщения (простая эвристика)
            # Ищем бэкапы в диапазоне message_id - 20 до message_id - 1
            deleted_count = 0
            for offset in range(1, 20):  # Проверяем последние 20 сообщений
                try:
                    old_message_id = current_message_id - offset
                    if old_message_id <= 0:
                        break
                    
                    # Пробуем удалить сообщение
                    delete_response = httpx.post(
                        f"{self.storage.base_url}/deleteMessage",
                        data={
                            'chat_id': self.storage.channel_id,
                            'message_id': old_message_id
                        },
                        timeout=10.0
                    )
                    
                    if delete_response.status_code == 200 and delete_response.json().get('ok'):
                        deleted_count += 1
                        print(f"🗑️  Deleted old backup message: {old_message_id}")
                        
                        # Останавливаемся после удаления достаточного количества
                        # Оставляем keep_count последних бэкапов
                        if deleted_count >= (20 - keep_count):
                            break
                except Exception:
                    # Сообщение не существует или уже удалено - это нормально
                    continue
            
            if deleted_count > 0:
                print(f"✅ Cleaned up {deleted_count} old backup(s)")
            else:
                print("ℹ️  No old backups to clean up")
                
        except Exception as e:
            print(f"⚠️  Error during backup cleanup: {e}")
            # Не критично, продолжаем работу
    
