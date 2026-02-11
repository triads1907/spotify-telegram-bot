"""
Обработчики команд для администраторов
"""
from telegram import Update
from telegram.ext import ContextTypes
import config
import os
from services.telegram_storage_service import TelegramStorageService
from services.db_backup_service import DatabaseBackupService

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ручное создание backup БД (только для админов)
    Команда: /backup
    """
    user_id = update.effective_user.id
    
    # Проверка прав администратора
    if user_id not in config.ADMIN_IDS:
        print(f"🚫 Unauthorized backup attempt by {user_id}")
        return

    msg = await update.message.reply_text("⏳ Начинаю создание бэкапа базы данных...")
    
    try:
        db = context.bot_data.get('db')
        storage_service = TelegramStorageService()
        db_path = config.DATABASE_URL.replace('sqlite+aiosqlite:///', '')
        
        backup_service = DatabaseBackupService(
            storage_service=storage_service,
            db_path=db_path,
            db_manager=db
        )
        
        # Выполняем бэкап
        success = await backup_service.backup_to_telegram()
        
        if success:
            await msg.edit_text("✅ <b>Бэкап успешно создан и закреплен в канале!</b>", parse_mode='HTML')
            print(f"📦 Manual backup triggered by {user_id} successful.")
        else:
            await msg.edit_text("❌ <b>Ошибка при создании бэкапа.</b> Проверьте логи сервера.", parse_mode='HTML')
            
    except Exception as e:
        print(f"❌ Error in manual backup command: {e}")
        await msg.edit_text(f"❌ <b>Произошла ошибка:</b>\n<code>{str(e)}</code>", parse_mode='HTML')
