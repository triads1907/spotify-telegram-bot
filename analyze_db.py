
import asyncio
import os
import sys
from sqlalchemy import select, func, or_

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import DatabaseManager
from database.models import Track, TrackCache, TelegramFile, DownloadHistory

async def analyze():
    db = DatabaseManager()
    await db.init_db()
    async with db.async_session() as session:
        # Total tracks
        tracks_count = await session.execute(select(func.count(Track.id)))
        print(f"Total Tracks in DB: {tracks_count.scalar()}")
        
        # Tracks with telegram_file_id
        cached_tracks = await session.execute(select(func.count(Track.id)).where(Track.telegram_file_id != None))
        print(f"Tracks with telegram_file_id set: {cached_tracks.scalar()}")
        
        # TrackCache entries
        cache_entries = await session.execute(select(func.count(TrackCache.id)))
        print(f"Total TrackCache entries: {cache_entries.scalar()}")
        
        # TelegramFile entries
        tg_files = await session.execute(select(func.count(TelegramFile.track_id)))
        print(f"Total TelegramFile entries: {tg_files.scalar()}")
        
        # Download history
        history = await session.execute(select(func.count(DownloadHistory.id)))
        print(f"Total Download History entries: {history.scalar()}")
        
        # Sample of last 5 tracks from new get_library_tracks logic
        result = await session.execute(
            select(Track)
            .outerjoin(TrackCache, Track.id == TrackCache.track_id)
            .outerjoin(TelegramFile, Track.id == TelegramFile.track_id)
            .where(or_(
                Track.telegram_file_id != None,
                TrackCache.id != None,
                TelegramFile.track_id != None
            ))
            .group_by(Track.id)
            .order_by(func.coalesce(func.max(TelegramFile.uploaded_at), func.max(TrackCache.created_at), Track.created_at).desc())
            .limit(5)
        )
        print("\nLast 5 Library Tracks (by New Logic):")
        for track in result.scalars().all():
            print(f"- {track.artist} - {track.name} (Created: {track.created_at})")

if __name__ == "__main__":
    asyncio.run(analyze())
