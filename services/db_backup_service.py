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
            print("🔍 Checking for latest backup in Telegram pinned message...")
            backup_info = await self._find_latest_backup()
            
            if not backup_info:
                print("ℹ️  No backup found in Telegram, using local database (if exists)")
                return False
            
            # Если локальный файл существует, проверим, нужно ли его заменять
            if os.path.exists(self.db_path):
                file_size = os.path.getsize(self.db_path)
                # Если файл подозрительно маленький (свежесозданный) - заменяем без вопросов
                if file_size < 32768: # 32KB - это примерно пустая БД со схемой
                    print(f"⚠️  Local database is too small ({file_size} bytes), overwriting with backup...")
                else:
                    print(f"✅ Local database exists and looks healthy ({file_size} bytes). Skipping restoration.")
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
                
                # Cleanup old backups (keep only last 2)
                await self.cleanup_old_backups(keep_count=2)
                
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
                
                # Создаем директорию если её нет
                os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
                
                shutil.move(temp_path, self.db_path)
                
                # Явно устанавливаем права на запись (chmod 666)
                try:
                    os.chmod(self.db_path, 0o666)
                except Exception as chmod_e:
                    print(f"⚠️  Warning: Could not set permissions: {chmod_e}")
                
                print(f"✅ Database file restored and permissions set: {self.db_path}")
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
 
          
         a s y n c   d e f   c l e a n u p _ o l d _ b a c k u p s ( s e l f ,   k e e p _ c o u n t :   i n t   =   2 ) :  
                 " " "  
                   � �  �  Q! !
  !!  � !!9  �    � ! T �  W!9       ,    U!!  �   Q   !  U � !
 T U   W U! �  �  �  Q �   k e e p _ c o u n t  
                  
                 A r g s :  
                         k e e p _ c o u n t :    Y U �  Q!!  � !!   U   W U! �  �  �  Q!&    � ! T �  W U    � � !  ! U!& ! �   �   Q!  (  W U  !S X U � !!  �   Q!  2 )  
                 " " "  
                 t r y :  
                         p r i n t ( f " @_� !  C l e a n i n g   u p   o l d   b a c k u p s   ( k e e p i n g   l a s t   { k e e p _ c o u n t } ) . . . " )  
                          
                         #    _ U � !S!!  �  �  X   �  �  T! �  W �  �    U �   ! U U � !0  �   Q �   (  W U! �  �  �  Q !   � ! T �  W)  
                         p i n n e d   =   s e l f . s t o r a g e . g e t _ p i n n e d _ m e s s a g e ( )  
                         i f   n o t   p i n n e d   o r   n o t   p i n n e d . g e t ( ' d o c u m e n t ' ) :  
                                 p r i n t ( " 2 !?Q    N o   p i n n e d   b a c k u p   f o u n d ,   s k i p p i n g   c l e a n u p " )  
                                 r e t u r n  
                          
                         c u r r e n t _ m e s s a g e _ i d   =   p i n n e d . g e t ( ' m e s s a g e _ i d ' )  
                         i f   n o t   c u r r e n t _ m e s s a g e _ i d :  
                                 r e t u r n  
                          
                         #    _! U � !S �  X  !S � �  �  Q! !
   W! �  �!9  �!S!0  Q �   ! U U � !0  �   Q!  (  W! U!!  � !  ! ! Q!!  Q T � )  
                         #    � !0  �  X   � ! T �  W!9       � Q �  W �  �  U  �   m e s s a g e _ i d   -   2 0    � U  m e s s a g e _ i d   -   1  
                         d e l e t e d _ c o u n t   =   0  
                         f o r   o f f s e t   i n   r a n g e ( 1 ,   2 0 ) :     #    _! U  � !! �  X   W U! �  �  �  Q �   2 0   ! U U � !0  �   Q ! 
                                 t r y :  
                                         o l d _ m e s s a g e _ i d   =   c u r r e n t _ m e s s a g e _ i d   -   o f f s e t  
                                         i f   o l d _ m e s s a g e _ i d   < =   0 :  
                                                 b r e a k  
                                          
                                         #    _! U � !S �  X  !S � �  �  Q! !
  ! U U � !0  �   Q �  
                                         d e l e t e _ r e s p o n s e   =   h t t p x . p o s t (  
                                                 f " { s e l f . s t o r a g e . b a s e _ u r l } / d e l e t e M e s s a g e " ,  
                                                 d a t a = {  
                                                         ' c h a t _ i d ' :   s e l f . s t o r a g e . c h a n n e l _ i d ,  
                                                         ' m e s s a g e _ i d ' :   o l d _ m e s s a g e _ i d  
                                                 } ,  
                                                 t i m e o u t = 1 0 . 0  
                                         )  
                                          
                                         i f   d e l e t e _ r e s p o n s e . s t a t u s _ c o d e   = =   2 0 0   a n d   d e l e t e _ r e s p o n s e . j s o n ( ) . g e t ( ' o k ' ) :  
                                                 d e l e t e d _ c o u n t   + =   1  
                                                 p r i n t ( f " @_  ?Q    D e l e t e d   o l d   b a c k u p   m e s s a g e :   { o l d _ m e s s a g e _ i d } " )  
                                                  
                                                 #    [!!  �   �   �  Q  �  �  X!!   W U! �  �   !S � �  �  �   Q!   � U!!  � !  U!!   U V U   T U �  Q!!  � !!   �  
                                                 #    [!!  �   � ! �  X  k e e p _ c o u n t    W U! �  �  �  Q!&    � ! T �  W U  
                                                 i f   d e l e t e d _ c o u n t   > =   ( 2 0   -   k e e p _ c o u n t ) :  
                                                         b r e a k  
                                 e x c e p t   E x c e p t i o n :  
                                         #     U U � !0  �   Q �     �   !!S!0  � !!  !S � !    Q �  Q  !S �  �   !S � �  �  �   U  -   !!  U    U! X �  � !
  U 
                                         c o n t i n u e  
                          
                         i f   d e l e t e d _ c o u n t   >   0 :  
                                 p r i n t ( f " 2Z&   C l e a n e d   u p   { d e l e t e d _ c o u n t }   o l d   b a c k u p ( s ) " )  
                         e l s e :  
                                 p r i n t ( " 2 !?Q    N o   o l d   b a c k u p s   t o   c l e a n   u p " )  
                                  
                 e x c e p t   E x c e p t i o n   a s   e :  
                         p r i n t ( f " 2Y� ?Q    E r r o r   d u r i n g   b a c k u p   c l e a n u p :   { e } " )  
                         #    \ �    T! Q!  Q!!   U,    W! U � U �  �  �  �  X  ! �  �  U! !S 
 