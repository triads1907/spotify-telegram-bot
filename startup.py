import subprocess
import sys
import os
import time
import signal
import asyncio
import config
from database.db_manager import DatabaseManager

async def pre_startup_db_init():
    """
    Централизованная инициализация БД перед запуском всех сервисов.
    Выполняется ОДИН РАЗ в родительском процессе.
    """
    print("=" * 80)
    print("🏗️  PRE-STARTUP DATABASE INITIALIZATION")
    print("=" * 80)
    
    try:
        db = DatabaseManager()
        
        # 1. Восстановление из Telegram
        print("📦 [INIT] Checking for database restoration from Telegram...")
        from services.telegram_storage_service import TelegramStorageService
        from services.db_backup_service import DatabaseBackupService
        
        storage = TelegramStorageService()
        db_path = config.DATABASE_URL.replace('sqlite+aiosqlite:///', '')
        backup_service = DatabaseBackupService(storage_service=storage, db_path=db_path, db_manager=db)
        
        restored = await backup_service.restore_from_telegram()
        if restored:
            print("🔄 [INIT] Database restored! Refreshing engine...")
            await db.reconnect()
        else:
            print("ℹ️  [INIT] No backup found or restore skipped.")
            
        # 2. Инициализация схемы и WAL mode
        print("📦 [INIT] Ensuring database schema and WAL mode...")
        await db.init_db()
        
        # Закрываем соединение, так как воркеры откроют свои
        await db.close()
        
        print("✅ [INIT] Database is READY for services.")
        print("=" * 80)
        return True
    except Exception as e:
        print(f"❌ [INIT] Database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🚀 Starting Spotify Telegram Bot system...")

    # Set environment variables if needed
    env = os.environ.copy()
    
    # Processes list
    processes = []

    try:
        # 0. Инициализация БД перед запуском всех сервисов
        success = asyncio.run(pre_startup_db_init())
        if not success:
            print("⚠️  Warning: Pre-startup database initialization failed. Continuing...")

        # Enable unbuffered output for the web process
        web_env = env.copy()
        web_env['PYTHONUNBUFFERED'] = '1'
        port = env.get('PORT', '5000')
        
        print(f"🔗 Starting Web Interface (Gunicorn) on port {port}...")
        web_process = subprocess.Popen(
            ["gunicorn", "--bind", f"0.0.0.0:{port}", "--workers", "1", "--timeout", "120", "web.app:app"],
            env=web_env,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        processes.append(web_process)

        # 2. Start Telegram Bot
        print("🤖 Starting Telegram Bot...")
        bot_process = subprocess.Popen(
            [sys.executable, "bot.py"],
            env=env,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        processes.append(bot_process)

        print("✅ All processes started. Monitoring...")

        # Monitor processes
        while True:
            for p in processes:
                if p.poll() is not None:
                    print(f"❌ Process exited with code {p.returncode}")
                    # If one process dies, we exit to let Railway restart the container
                    return p.returncode
            time.sleep(10)

    except KeyboardInterrupt:
        print("\n👋 Stopping system...")
        for p in processes:
            p.terminate()
        return 0
    except Exception as e:
        print(f"❌ Startup error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
