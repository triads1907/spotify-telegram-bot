import subprocess
import sys
import os
import time
import signal

def main():
    print("🚀 Starting Spotify Telegram Bot system...")

    # Set environment variables if needed
    env = os.environ.copy()
    
    # Processes list
    processes = []

    try:
        # 1. Start Web App
        print("🔗 Starting Web Interface (Flask)...")
        web_process = subprocess.Popen(
            [sys.executable, "web/app.py"],
            env=env,
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
