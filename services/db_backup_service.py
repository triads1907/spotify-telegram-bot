"""
Database Backup Service - автоматический backup и восстановление БД через Telegram
"""
import os
import asyncio
import shutil
from datetime import datetime
from typing import Optional
import httpx


class DatabaseBackupService:
    """Сервис для backup и восстановления БД через Telegram Storage"""
    
    def __init__(self, storage_service, db_path: str):
        """
        Args:
            storage_service: TelegramStorageService instance
            db_path: Путь к файлу БД (например, 'spotify_bot.db')
        """
        self.storage = storage_service
        self.db_path = db_path
        self.backup_file_id = None
        self.is_running = False
        
        print(f"📦 Database Backup Service initialized for: {db_path}")
    
    async def restore_from_telegram(self) -> bool:
        """
        Восстановить БД из Telegram при старте приложения
        
        Returns:
            True если БД успешно восстановлена, False если backup не найден
        """
        try:
            print("🔍 Checking for database backup in Telegram...")
            
            # Проверяем, существует ли уже локальная БД
            if os.path.exists(self.db_path):
                file_size = os.path.getsize(self.db_path)
                print(f"ℹ️  Local database exists ({file_size} bytes)")
                
                # Если БД пустая или очень маленькая, попробуем восстановить
                if file_size < 1024:  # Меньше 1KB
                    print("⚠️  Local database is too small, attempting restore...")
                else:
                    print("✅ Using existing local database")
                    return True
            
            # Ищем последний backup в Telegram
            backup_info = await self._find_latest_backup()
            
            if not backup_info:
                print("ℹ️  No backup found in Telegram, will create new database")
                return False
            
            # Скачиваем backup
            print(f"📥 Downloading database backup from Telegram...")
            success = await self._download_backup(backup_info['file_id'])
            
            if success:
                print("✅ Database successfully restored from Telegram!")
                self.backup_file_id = backup_info['file_id']
                return True
            else:
                print("❌ Failed to restore database from Telegram")
                return False
                
        except Exception as e:
            print(f"❌ Error restoring database: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def backup_to_telegram(self) -> bool:
        """
        Создать backup БД в Telegram
        
        Returns:
            True если backup успешно создан
        """
        try:
            if not os.path.exists(self.db_path):
                print(f"⚠️  Database file not found: {self.db_path}")
                return False
            
            file_size = os.path.getsize(self.db_path)
            print(f"💾 Creating database backup ({file_size / 1024:.2f} KB)...")
            
            # Загружаем БД как document в Telegram
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            caption = f"🗄️ Database Backup - {timestamp}"
            
            result = self.storage.upload_document(self.db_path, caption)
            
            if result and result.get('file_id'):
                self.backup_file_id = result['file_id']
                print(f"✅ Database backup created: {result['file_id'][:20]}...")
                
                # Закрепляем сообщение, чтобы бот всегда мог его найти
                if result.get('message_id'):
                    pin_success = self.storage.pin_message(result['message_id'])
                    if pin_success:
                        print(f"📌 Backup message pinned: {result['message_id']}")
                
                return True
            else:
                print("❌ Failed to create database backup")
                return False
                
        except Exception as e:
            print(f"❌ Error creating backup: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def start_periodic_backup(self, interval: int = 300):
        """
        Запустить периодический backup БД
        
        Args:
            interval: Интервал в секундах (по умолчанию 300 = 5 минут)
        """
        self.is_running = True
        print(f"⏰ Starting periodic database backup (every {interval} seconds)...")
        
        while self.is_running:
            try:
                await asyncio.sleep(interval)
                
                if self.is_running:
                    await self.backup_to_telegram()
                    
            except asyncio.CancelledError:
                print("🛑 Periodic backup cancelled")
                break
            except Exception as e:
                print(f"❌ Error in periodic backup: {e}")
                # Продолжаем работу даже при ошибке
                continue
    
    def stop_periodic_backup(self):
        """Остановить периодический backup"""
        print("🛑 Stopping periodic database backup...")
        self.is_running = False
    
    async def _find_latest_backup(self) -> Optional[dict]:
        """
        Найти последний backup БД в Telegram канале
        
        Returns:
            Dict с информацией о backup или None
        """
        try:
            # Получаем закрепленное сообщение из канала
            message = self.storage.get_pinned_message()
            
            if not message or not message.get('document'):
                # Если закрепленного сообщения нет, попробуем поискать в последних сообщениях (но это менее надежно)
                print("ℹ️  No pinned message found in channel")
                return None
            
            doc = message['document']
            # Проверяем, что это файл БД
            if doc.get('file_name', '').endswith('.db'):
                print(f"✅ Found backup in pinned message: {doc.get('file_name')}")
                return {
                    'file_id': doc['file_id'],
                    'file_name': doc.get('file_name'),
                    'file_size': doc.get('file_size'),
                    'date': message.get('date')
                }
            
            return None
            
        except Exception as e:
            print(f"❌ Error finding backup: {e}")
            return None
    
    async def _download_backup(self, file_id: str) -> bool:
        """
        Скачать backup из Telegram
        
        Args:
            file_id: ID файла в Telegram
            
        Returns:
            True если успешно скачан
        """
        try:
            # Создаем временный файл для backup
            temp_path = f"{self.db_path}.backup"
            
            # Скачиваем файл
            success = self.storage.download_file(file_id, temp_path)
            
            if success and os.path.exists(temp_path):
                # Заменяем текущую БД на backup
                if os.path.exists(self.db_path):
                    os.remove(self.db_path)
                
                shutil.move(temp_path, self.db_path)
                print(f"✅ Database file restored: {self.db_path}")
                return True
            else:
                print("❌ Failed to download backup file")
                return False
                
        except Exception as e:
            print(f"❌ Error downloading backup: {e}")
            return False
    
        except Exception as e:
            print(f"❌ Error downloading backup: {e}")
            return False
