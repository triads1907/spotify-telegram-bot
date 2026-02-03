"""
Сервис для скачивания музыки через yt-dlp
"""
import os
import asyncio
from typing import Optional, Dict
import yt_dlp
import httpx


class DownloadService:
    """Сервис для поиска и скачивания музыки с YouTube"""
    
    def __init__(self, download_dir: str = "downloads"):
        # Всегда используем абсолютный путь относительно корня проекта
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.download_dir = os.path.join(base_dir, download_dir)
        os.makedirs(self.download_dir, exist_ok=True)
        
    def _get_ffmpeg_args(self, quality: str, file_format: str) -> list:
        """Получить аргументы ffmpeg на основе качества и формата"""
        if file_format != 'flac':
            return []
            
        if quality == '1411':
            return ['-af', 'aresample=44100', '-sample_fmt', 's16']
        elif quality == '4600':
            return ['-af', 'aresample=96000', '-sample_fmt', 's32']
        elif quality == '9200':
            return ['-af', 'aresample=192000', '-sample_fmt', 's32']
        return []
    
    async def search_and_download(self, artist: str, track_name: str, quality: str = '192', file_format: str = 'mp3') -> Optional[Dict]:
        """
        Поиск и скачивание трека с YouTube
        """
        ffmpeg_args = self._get_ffmpeg_args(quality, file_format)
        search_query = f"{artist} - {track_name}"
        
        # Модифицируем шаблон имени файла чтобы избежать коллизий качества
        safe_name = "".join([c if c.isalnum() or c in " -_" else "_" for c in f"{artist} - {track_name}"])
        out_tmpl = os.path.join(self.download_dir, f"{safe_name}_{quality}.%(ext)s")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': out_tmpl,
            'overwrites': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': file_format,
                'preferredquality': quality if file_format == 'mp3' else None,
            }],
            'postprocessor_args': {
                'ffmpeg': ffmpeg_args
            } if ffmpeg_args else {},
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'default_search': 'ytsearch1',
        }
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                self._download_sync, 
                search_query, 
                ydl_opts,
                file_format
            )
            return result
        except Exception as e:
            print(f"❌ Ошибка скачивания {search_query}: {e}")
            return None
    
    def _download_sync(self, query: str, ydl_opts: dict, file_format: str = 'mp3') -> Optional[Dict]:
        """Синхронное скачивание (для запуска в executor)"""
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=True)
                
                if not info:
                    return None
                
                title = info.get('title', 'Unknown')
                duration = info.get('duration', 0)
                
                import glob
                import time
                
                # 1. Пробуем предсказанный путь
                base_path = ydl.prepare_filename(info)
                file_path = os.path.splitext(base_path)[0] + f'.{file_format}'
                
                # 2. Если не найден, пробуем путь из метаданных yt-dlp
                if not os.path.exists(file_path):
                    actual_filename = info.get('_filename')
                    if actual_filename:
                        potential_path = os.path.splitext(actual_filename)[0] + f'.{file_format}'
                        if os.path.exists(potential_path):
                            file_path = potential_path
                
                # 3. Если всё еще не найден (самый надежный способ для сложных имен), 
                # ищем файл с нужным форматом, созданный в последние 60 секунд
                if not os.path.exists(file_path):
                    pattern = os.path.join(self.download_dir, f'*.{file_format}')
                    files = glob.glob(pattern)
                    now = time.time()
                    # Берем те, что созданы недавно
                    recent_files = [f for f in files if now - os.path.getctime(f) < 60]
                    if recent_files:
                        # Берем самый новый из недавних
                        file_path = max(recent_files, key=os.path.getctime)
                
                # 4. Проверяем финальный путь
                file_size = 0
                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                else:
                    # Логируем неудачу для отладки
                    print(f"⚠️ Файл не найден после всех попыток: {file_path}")
                    # Попробуем взять просто самый последний файл этого формата (крайняя мера)
                    pattern = os.path.join(self.download_dir, f'*.{file_format}')
                    all_files = glob.glob(pattern)
                    if all_files:
                        file_path = max(all_files, key=os.path.getctime)
                        file_size = os.path.getsize(file_path)
                
                return {
                    'file_path': file_path,
                    'title': title,
                    'duration': duration,
                    'artist': info.get('artist', ''),
                    'thumbnail': info.get('thumbnail', ''),
                    'file_size': file_size
                }
        except Exception as e:
            print(f"❌ Ошибка в _download_sync: {e}")
            return None

    
    async def search_and_download_by_query(self, search_query: str, quality: str = '192', file_format: str = 'mp3') -> Optional[Dict]:
        ffmpeg_args = self._get_ffmpeg_args(quality, file_format)
        
        # Модифицируем шаблон имени файла чтобы избежать коллизий качества
        safe_query = "".join([c if c.isalnum() or c in " -_" else "_" for c in search_query])
        out_tmpl = os.path.join(self.download_dir, f"{safe_query}_{quality}.%(ext)s")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': out_tmpl,
            'overwrites': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': file_format,
                'preferredquality': quality if file_format == 'mp3' else None,
            }],
            'postprocessor_args': {
                'ffmpeg': ffmpeg_args
            } if ffmpeg_args else {},
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'default_search': 'ytsearch1',
        }
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                self._download_sync, 
                search_query, 
                ydl_opts,
                file_format
            )
            return result
        except Exception as e:
            print(f"❌ Ошибка скачивания {search_query}: {e}")
            return None
    
    async def get_youtube_url(self, artist: str, track_name: str) -> Optional[str]:
        """
        Получить URL видео на YouTube без скачивания
        """
        search_query = f"{artist} - {track_name} audio"
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch1',
        }
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._get_url_sync,
                search_query,
                ydl_opts
            )
            return result
        except Exception as e:
            print(f"❌ Ошибка получения URL: {e}")
            return None
    
    def _get_url_sync(self, query: str, ydl_opts: dict) -> Optional[str]:
        """Синхронное получение URL"""
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)
                if info and 'entries' in info:
                    # Берем первый результат поиска
                    first_result = info['entries'][0]
                    return f"https://www.youtube.com/watch?v={first_result['id']}"
                elif info:
                    return info.get('webpage_url')
        except Exception as e:
            print(f"❌ Ошибка в _get_url_sync: {e}")
            return None
    
    async def download_image(self, url: str) -> Optional[str]:
        """Скачать изображение во временный файл"""
        if not url:
            return None
            
        try:
            # Используем хеш URL для имени файла чтобы не скачивать одно и то же
            import hashlib
            file_hash = hashlib.md5(url.encode()).hexdigest()
            file_path = os.path.join(self.download_dir, f"thumb_{file_hash}.jpg")
            
            if os.path.exists(file_path):
                return file_path
                
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10.0)
                if response.status_code == 200:
                    with open(file_path, 'wb') as f:
                        f.write(response.content)
                    return file_path
        except Exception as e:
            print(f"❌ Ошибка скачивания обложки: {e}")
            
        return None

    def cleanup_file(self, file_path: str):
        """Удалить скачанный файл"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"🗑️ Удален файл: {file_path}")
        except Exception as e:
            print(f"❌ Ошибка удаления файла {file_path}: {e}")
