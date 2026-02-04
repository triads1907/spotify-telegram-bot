    
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
