from __future__ import annotations
"""
Менеджер базы данных для работы с SQLite
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, delete
from typing import Optional, List
from datetime import datetime, timedelta

from .models import Base, User, Playlist, Track, PlaylistTrack, Album, DownloadHistory, Favorite, TrackCache, AuthToken, TelegramFile
import config


class DatabaseManager:
    """Менеджер для асинхронной работы с базой данных"""
    
    def __init__(self, database_url: str = None):
        self.database_url = database_url or config.DATABASE_URL
        # Добавляем таймаут для SQLite чтобы избежать "database is locked" в многопроцессной среде
        connect_args = {"timeout": 20} if "sqlite" in self.database_url else {}
        self.engine = create_async_engine(
            self.database_url, 
            echo=False,
            connect_args=connect_args
        )
        self.async_session = async_sessionmaker(
            self.engine, 
            class_=AsyncSession, 
            expire_on_commit=False
        )
    
    async def init_db(self):
        """Инициализация базы данных и создание таблиц"""
        async with self.engine.begin() as conn:
            # Включаем WAL mode для лучшей параллельности в SQLite
            if "sqlite" in self.database_url:
                await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.run_sync(Base.metadata.create_all)
        print("✅ База данных инициализирована (WAL mode enabled)")
    
    async def close(self):
        """Закрытие соединения с БД"""
        await self.engine.dispose()
    
    # ========== ПОЛЬЗОВАТЕЛИ ==========
    
    async def get_or_create_user(self, user_id: int, tg_user_or_username: any = None, 
                                  first_name: str = None, last_name: str = None,
                                  username: str = None) -> User:
        """Получить или создать пользователя"""
        # Более надежный способ извлечения данных из объекта пользователя
        if tg_user_or_username and not isinstance(tg_user_or_username, str):
            tg_user = tg_user_or_username
            username = getattr(tg_user, 'username', None)
            # Приоритет отдаем переданным аргументам, если они не None
            first_name = first_name or getattr(tg_user, 'first_name', None)
            last_name = last_name or getattr(tg_user, 'last_name', None)
        else:
            username = tg_user_or_username

        async with self.async_session() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            
            if not user:
                user = User(
                    id=user_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                print(f"✅ Создан новый пользователь: {user_id}")
            else:
                # Обновляем last_active
                user.last_active = datetime.utcnow()
                # Также обновляем информацию о пользователе, если она изменилась
                if username: user.username = username
                if first_name: user.first_name = first_name
                if last_name: user.last_name = last_name
                await session.commit()
            
            return user
    
    # ========== ПЛЕЙЛИСТЫ ==========
    
    async def create_playlist(self, user_id: int, name: str, description: str = None) -> Playlist:
        """Создать новый плейлист"""
        async with self.async_session() as session:
            playlist = Playlist(
                user_id=user_id,
                name=name,
                description=description
            )
            session.add(playlist)
            await session.commit()
            await session.refresh(playlist)
            return playlist
    
    async def get_user_playlists(self, user_id: int) -> List[Playlist]:
        """Получить все плейлисты пользователя"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Playlist)
                .where(Playlist.user_id == user_id)
                .order_by(Playlist.created_at.desc())
            )
            return list(result.scalars().all())
    
    async def get_playlist(self, playlist_id: int) -> Optional[Playlist]:
        """Получить плейлист по ID"""
        async with self.async_session() as session:
            result = await session.execute(select(Playlist).where(Playlist.id == playlist_id))
            return result.scalar_one_or_none()
    
    async def delete_playlist(self, playlist_id: int) -> bool:
        """Удалить плейлист"""
        async with self.async_session() as session:
            result = await session.execute(delete(Playlist).where(Playlist.id == playlist_id))
            await session.commit()
            return result.rowcount > 0
    
    # ========== ТРЕКИ ==========
    
    async def get_or_create_track(self, track_data: dict) -> Track:
        """Получить или создать трек"""
        async with self.async_session() as session:
            track_id = track_data['id']
            result = await session.execute(select(Track).where(Track.id == track_id))
            track = result.scalar_one_or_none()
            
            if not track:
                track = Track(**track_data)
                session.add(track)
                await session.commit()
                await session.refresh(track)
            
            return track
    
    async def get_track(self, track_id: str) -> Optional[Track]:
        """Получить трек по ID"""
        async with self.async_session() as session:
            result = await session.execute(select(Track).where(Track.id == track_id))
            return result.scalar_one_or_none()
    
    # ========== ТРЕКИ В ПЛЕЙЛИСТАХ ==========
    
    async def add_track_to_playlist(self, playlist_id: int, track_id: str) -> bool:
        """Добавить трек в плейлист"""
        async with self.async_session() as session:
            # Проверяем, не добавлен ли уже трек
            result = await session.execute(
                select(PlaylistTrack)
                .where(PlaylistTrack.playlist_id == playlist_id)
                .where(PlaylistTrack.track_id == track_id)
            )
            existing = result.scalars().first()
            
            if existing:
                return False  # Трек уже в плейлисте
            
            # Получаем максимальную позицию
            result = await session.execute(
                select(PlaylistTrack.position)
                .where(PlaylistTrack.playlist_id == playlist_id)
                .order_by(PlaylistTrack.position.desc())
            )
            max_position = result.scalars().first()
            new_position = (max_position or 0) + 1
            
            # Добавляем трек
            playlist_track = PlaylistTrack(
                playlist_id=playlist_id,
                track_id=track_id,
                position=new_position
            )
            session.add(playlist_track)
            
            # Обновляем время изменения плейлиста
            playlist_result = await session.execute(select(Playlist).where(Playlist.id == playlist_id))
            playlist = playlist_result.scalar_one_or_none()
            if playlist:
                playlist.updated_at = datetime.utcnow()
            
            await session.commit()
            return True
    
    async def get_playlist_tracks(self, playlist_id: int) -> List[Track]:
        """Получить все треки плейлиста"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Track)
                .join(PlaylistTrack)
                .where(PlaylistTrack.playlist_id == playlist_id)
                .order_by(PlaylistTrack.position)
            )
            return list(result.scalars().all())
    
    async def remove_track_from_playlist(self, playlist_id: int, track_id: str) -> bool:
        """Удалить трек из плейлиста"""
        async with self.async_session() as session:
            result = await session.execute(
                delete(PlaylistTrack)
                .where(PlaylistTrack.playlist_id == playlist_id)
                .where(PlaylistTrack.track_id == track_id)
            )
            await session.commit()
            return result.rowcount > 0
    
    async def get_playlist_track_count(self, playlist_id: int) -> int:
        """Получить количество треков в плейлисте"""
        async with self.async_session() as session:
            result = await session.execute(
                select(PlaylistTrack)
                .where(PlaylistTrack.playlist_id == playlist_id)
            )
            return len(list(result.scalars().all()))
    
    # ========== ИСТОРИЯ СКАЧИВАНИЙ (Функция 5) ==========
    
    async def add_download_to_history(self, user_id: int, track_id: str, quality: str = '192', file_size: int = 0):
        """Добавить запись в историю скачиваний"""
        async with self.async_session() as session:
            history_entry = DownloadHistory(
                user_id=user_id,
                track_id=track_id,
                quality=quality,
                file_size_mb=file_size // (1024 * 1024)  # Конвертируем в MB
            )
            session.add(history_entry)
            
            # Обновляем статистику пользователя
            user_result = await session.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            if user:
                user.total_downloads += 1
                user.total_size_mb += file_size // (1024 * 1024)
            
            # Обновляем счётчик скачиваний трека
            track_result = await session.execute(select(Track).where(Track.id == track_id))
            track = track_result.scalar_one_or_none()
            if track:
                track.download_count += 1
            
            await session.commit()
    
    async def get_download_history(self, user_id: int, limit: int = 10):
        """Получить историю скачиваний пользователя"""
        async with self.async_session() as session:
            result = await session.execute(
                select(DownloadHistory, Track)
                .join(Track, DownloadHistory.track_id == Track.id)
                .where(DownloadHistory.user_id == user_id)
                .order_by(DownloadHistory.downloaded_at.desc())
                .limit(limit)
            )
            
            history = []
            for download, track in result.all():
                history.append({
                    'track': {
                        'id': track.id,
                        'name': track.name,
                        'artist': track.artist,
                        'spotify_url': track.spotify_url
                    },
                    'downloaded_at': download.downloaded_at,
                    'quality': download.quality,
                    'file_size_mb': download.file_size_mb
                })
            
            return history
    
    async def clear_download_history(self, user_id: int):
        """Очистить историю скачиваний пользователя"""
        async with self.async_session() as session:
            await session.execute(
                delete(DownloadHistory).where(DownloadHistory.user_id == user_id)
            )
            await session.commit()
    
    # ========== ИЗБРАННОЕ (Функция 8) ==========
    
    async def add_to_favorites(self, user_id: int, track_id: str):
        """Добавить трек в избранное"""
        async with self.async_session() as session:
            # Проверяем, не добавлен ли уже
            result = await session.execute(
                select(Favorite)
                .where(Favorite.user_id == user_id)
                .where(Favorite.track_id == track_id)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                return False  # Уже в избранном
            
            favorite = Favorite(user_id=user_id, track_id=track_id)
            session.add(favorite)
            await session.commit()
            return True
    
    async def remove_from_favorites(self, user_id: int, track_id: str):
        """Удалить трек из избранного"""
        async with self.async_session() as session:
            result = await session.execute(
                delete(Favorite)
                .where(Favorite.user_id == user_id)
                .where(Favorite.track_id == track_id)
            )
            await session.commit()
            return result.rowcount > 0
    
    async def get_favorites(self, user_id: int):
        """Получить избранные треки пользователя"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Favorite, Track)
                .join(Track, Favorite.track_id == Track.id)
                .where(Favorite.user_id == user_id)
                .order_by(Favorite.added_at.desc())
            )
            
            favorites = []
            for fav, track in result.all():
                favorites.append({
                    'track': {
                        'id': track.id,
                        'name': track.name,
                        'artist': track.artist,
                        'spotify_url': track.spotify_url,
                        'image_url': track.image_url
                    },
                    'added_at': fav.added_at
                })
            
            return favorites
    
    async def is_favorite(self, user_id: int, track_id: str) -> bool:
        """Проверить, находится ли трек в избранном"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Favorite)
                .where(Favorite.user_id == user_id)
                .where(Favorite.track_id == track_id)
            )
            return result.scalar_one_or_none() is not None
    
    # ========== НАСТРОЙКИ ПОЛЬЗОВАТЕЛЯ (Функция 3, 18) ==========
    
    async def update_user_setting(self, user_id: int, setting_name: str, value):
        """Обновить настройку пользователя"""
        async with self.async_session() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            
            if user:
                setattr(user, setting_name, value)
                await session.commit()
                return True
            return False
    
    async def get_user_quality(self, user_id: int) -> str:
        """Получить предпочитаемое качество пользователя"""
        async with self.async_session() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            return user.preferred_quality if user else '192'
    
    async def get_user_stats(self, user_id: int):
        """Получить статистику пользователя"""
        async with self.async_session() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            
            if not user:
                return None
            
            return {
                'total_downloads': user.total_downloads,
                'total_size_mb': user.total_size_mb,
                'member_since': user.created_at,
                'last_active': user.last_active
            }
    
    # ========== КЭШИРОВАНИЕ (Функция 10) ==========
    
    async def update_track_cache(self, track_id: str, telegram_file_id: str, 
                                 file_format: str = 'mp3', quality: str = '192'):
        """Обновить кэш трека (сохранить telegram_file_id в TrackCache)"""
        async with self.async_session() as session:
            # Проверяем, есть ли уже такой кэш (чтобы не дублировать)
            result = await session.execute(
                select(TrackCache)
                .where(TrackCache.track_id == track_id)
                .where(TrackCache.file_format == file_format)
                .where(TrackCache.quality == quality)
            )
            cache_entry = result.scalars().first()
            
            if cache_entry:
                cache_entry.telegram_file_id = telegram_file_id
                cache_entry.created_at = datetime.utcnow()
            else:
                cache_entry = TrackCache(
                    track_id=track_id,
                    telegram_file_id=telegram_file_id,
                    file_format=file_format,
                    quality=quality
                )
                session.add(cache_entry)
            
            # Также обновляем время кэширования в основном треке для статистики
            track_result = await session.execute(select(Track).where(Track.id == track_id))
            track = track_result.scalar_one_or_none()
            if track:
                track.telegram_file_id = telegram_file_id # Совместимость со старым кодом
                track.cached_at = datetime.utcnow()

            await session.commit()
            return True
    
    async def get_cached_file_id(self, track_id: str, file_format: str = 'mp3', 
                                 quality: str = '192') -> Optional[str]:
        """Получить telegram_file_id из кэша для конкретного формата и качества"""
        async with self.async_session() as session:
            result = await session.execute(
                select(TrackCache)
                .where(TrackCache.track_id == track_id)
                .where(TrackCache.file_format == file_format)
                .where(TrackCache.quality == quality)
            )
            cache_entry = result.scalars().first()
            
            if cache_entry:
                # Проверяем, не устарел ли кэш (7 дней)
                age = (datetime.utcnow() - cache_entry.created_at).days
                if age < 7:
                    return cache_entry.telegram_file_id
                else:
                    # Удаляем устаревший кэш
                    await session.delete(cache_entry)
                    await session.commit()
            
            return None

    async def get_library_tracks(self, limit: int = 200) -> List[Track]:
        """Получить все треки, которые есть в системе (библиотека канала), отсортированные по новизне"""
        from sqlalchemy import or_, func, case
        async with self.async_session() as session:
            # Используем подзапрос для получения максимальной даты активности для каждого трека
            # Это гарантирует, что недавно загруженные/кэшированные старые треки поднимутся вверх
            
            # Определяем дату последнего действия
            last_activity = func.max(
                case(
                    (TelegramFile.uploaded_at != None, TelegramFile.uploaded_at),
                    else_=case(
                        (TrackCache.created_at != None, TrackCache.created_at),
                        else_=Track.created_at
                    )
                )
            ).label('last_activity')

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
                .limit(limit)
            )
            return list(result.scalars().all())

    # ========== АУТЕНТИФИКАЦИЯ (WEB) ==========

    async def create_auth_token(self, user_id: int, token: str, expires_in_seconds: Optional[int] = None) -> AuthToken:
        """Создать токен для веб-авторизации (постоянный или временный)"""
        async with self.async_session() as session:
            # Сначала проверяем, есть ли уже токен у этого пользователя
            result = await session.execute(select(AuthToken).where(AuthToken.user_id == user_id).order_by(AuthToken.created_at.desc()))
            existing_token = result.scalars().first()
            
            if existing_token:
                return existing_token

            expires_at = None
            if expires_in_seconds:
                expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)
            
            new_token = AuthToken(
                token=token,
                user_id=user_id,
                expires_at=expires_at
            )
            session.add(new_token)
            await session.commit()
            return new_token

    async def verify_auth_token(self, token: str) -> Optional[User]:
        """Проверить токен и вернуть пользователя (без удаления токена)"""
        async with self.async_session() as session:
            # Ищем токен, который либо не истек, либо не имеет срока годности
            query = select(AuthToken).where(AuthToken.token == token)
            result = await session.execute(query)
            auth_token = result.scalars().first()
            
            if auth_token:
                # Если у токена есть срок годности, проверяем его
                if auth_token.expires_at and auth_token.expires_at < datetime.utcnow():
                    await session.delete(auth_token)
                    await session.commit()
                    return None
                    
                user_result = await session.execute(select(User).where(User.id == auth_token.user_id))
                user = user_result.scalar_one_or_none()
                
                # Постоянные ссылки НЕ удаляем после использования
                return user
            
            return None
    
    # ========== TELEGRAM STORAGE (Кеширование файлов) ==========
    
    async def save_telegram_file(self, track_id: str, file_id: str, file_path: str = None, 
                                 file_size: int = None, artist: str = None, track_name: str = None) -> TelegramFile:
        """Сохранить file_id в кеш"""
        async with self.async_session() as session:
            # Проверяем, есть ли уже запись
            result = await session.execute(
                select(TelegramFile).where(TelegramFile.track_id == track_id)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                # Обновляем существующую запись
                existing.file_id = file_id
                existing.telegram_file_path = file_path
                existing.file_size = file_size
                existing.uploaded_at = datetime.utcnow()
                if artist:
                    existing.artist = artist
                if track_name:
                    existing.track_name = track_name
                await session.commit()
                return existing
            else:
                # Создаем новую запись
                telegram_file = TelegramFile(
                    track_id=track_id,
                    file_id=file_id,
                    telegram_file_path=file_path,
                    file_size=file_size,
                    artist=artist,
                    track_name=track_name
                )
                session.add(telegram_file)
                await session.commit()
                return telegram_file
    
    async def get_telegram_file(self, track_id: str) -> Optional[TelegramFile]:
        """Получить file_id из кеша"""
        async with self.async_session() as session:
            result = await session.execute(
                select(TelegramFile).where(TelegramFile.track_id == track_id)
            )
            return result.scalar_one_or_none()
    
    async def telegram_file_exists(self, track_id: str) -> bool:
        """Проверить, есть ли файл в Telegram Storage"""
        telegram_file = await self.get_telegram_file(track_id)
        return telegram_file is not None
