
import asyncio
import os
import sys
from sqlalchemy import select

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import DatabaseManager
from database.models import Track, TrackCache, TelegramFile

async def migrate():
    db = DatabaseManager()
    await db.init_db()
    async with db.async_session() as session:
        # 1. Migrate from Track.telegram_file_id
        result = await session.execute(select(Track).where(Track.telegram_file_id != None))
        tracks = result.scalars().all()
        print(f"Found {len(tracks)} tracks with telegram_file_id")
        
        for track in tracks:
            # Check if TelegramFile already exists
            res = await session.execute(select(TelegramFile).where(TelegramFile.track_id == track.id))
            if not res.scalar_one_or_none():
                tg_file = TelegramFile(
                    track_id=track.id,
                    file_id=track.telegram_file_id,
                    artist=track.artist,
                    track_name=track.name,
                    uploaded_at=track.cached_at or track.created_at
                )
                session.add(tg_file)
        
        # 2. Migrate from TrackCache
        result = await session.execute(select(TrackCache))
        caches = result.scalars().all()
        print(f"Found {len(caches)} cache entries")
        
        for cache in caches:
            # Check if TelegramFile already exists
            res = await session.execute(select(TelegramFile).where(TelegramFile.track_id == cache.track_id))
            if not res.scalar_one_or_none():
                # Get track info
                track_res = await session.execute(select(Track).where(Track.id == cache.track_id))
                track = track_res.scalar_one_or_none()
                if track:
                    tg_file = TelegramFile(
                        track_id=cache.track_id,
                        file_id=cache.telegram_file_id,
                        artist=track.artist,
                        track_name=track.name,
                        uploaded_at=cache.created_at
                    )
                    session.add(tg_file)
        
        await session.commit()
        print("✅ Migration completed")

if __name__ == "__main__":
    asyncio.run(migrate())
