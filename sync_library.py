
import asyncio
import os
import sys
from datetime import datetime
from sqlalchemy import select, or_

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db_manager import DatabaseManager
from database.models import Track, TrackCache, TelegramFile

async def sync_discovery():
    print("🔄 Starting Discovery Sync...")
    db = DatabaseManager()
    await db.init_db()
    
    async with db.async_session() as session:
        # 1. Находим все треки, у которых есть file_id в старых таблицах, но нет в TelegramFile
        # Проверяем Track.telegram_file_id
        result = await session.execute(
            select(Track).where(Track.telegram_file_id != None)
        )
        tracks_with_legacy_id = result.scalars().all()
        print(f"🔍 Found {len(tracks_with_legacy_id)} tracks with legacy telegram_file_id")
        
        for track in tracks_with_legacy_id:
            # Проверяем, есть ли уже в TelegramFile
            tg_check = await session.get(TelegramFile, track.id)
            if not tg_check:
                print(f"➕ Adding {track.artist} - {track.name} to TelegramFile from legacy ID")
                new_file = TelegramFile(
                    track_id=track.id,
                    file_id=track.telegram_file_id,
                    artist=track.artist,
                    track_name=track.name,
                    uploaded_at=track.cached_at or track.created_at or datetime.utcnow()
                )
                session.add(new_file)
        
        # 2. Проверяем TrackCache
        result = await session.execute(
            select(TrackCache)
        )
        cache_entries = result.scalars().all()
        print(f"🔍 Found {len(cache_entries)} cache entries")
        
        for entry in cache_entries:
            tg_check = await session.get(TelegramFile, entry.track_id)
            if not tg_check:
                # Получаем инфо о треке
                track = await session.get(Track, entry.track_id)
                if track:
                    print(f"➕ Adding {track.artist} - {track.name} to TelegramFile from cache")
                    new_file = TelegramFile(
                        track_id=entry.track_id,
                        file_id=entry.telegram_file_id,
                        artist=track.artist,
                        track_name=track.name,
                        uploaded_at=entry.created_at or datetime.utcnow()
                    )
                    session.add(new_file)
        
        await session.commit()
        print("✅ Discovery Sync complete!")
        
        # 3. Финальная проверка количества
        result = await session.execute(select(TelegramFile))
        all_files = result.scalars().all()
        print(f"📊 Total tracks in Discover: {len(all_files)}")

if __name__ == "__main__":
    asyncio.run(sync_discovery())
