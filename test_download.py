"""
Тест скачивания трека
"""
import asyncio
import sys
sys.path.insert(0, 'd:/uktamaliyev/hack/1')

from services.download_service import DownloadService

async def test_download():
    print("🧪 Тест скачивания трека\n")
    
    downloader = DownloadService()
    
    # Тестируем с названием трека
    search_query = "Pique do Ombrinho"
    
    print(f"🔍 Поиск: {search_query}")
    print("⏳ Скачивание...")
    
    result = await downloader.search_and_download_by_query(search_query)
    
    if result:
        print(f"\n✅ Успешно скачано!")
        print(f"   📁 Файл: {result['file_path']}")
        print(f"   🎵 Название: {result['title']}")
        print(f"   ⏱️  Длительность: {result['duration']} сек")
        
        import os
        if os.path.exists(result['file_path']):
            print(f"   ✅ Файл существует!")
            print(f"   📊 Размер: {os.path.getsize(result['file_path']) / 1024 / 1024:.2f} MB")
        else:
            print(f"   ❌ Файл НЕ найден!")
    else:
        print("\n❌ Ошибка скачивания")

if __name__ == '__main__':
    asyncio.run(test_download())
