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
        
        # Путь к файлу кук (всегда используем абсолютный путь)
        self.cookies_path = os.path.join(base_dir, "cookies.txt")
        
        os.makedirs(self.download_dir, exist_ok=True)
        
        # Инициализация YouTube API (если доступен)
        self.youtube_api = None
        try:
            from services.youtube_api_service import YouTubeAPIService
            self.youtube_api = YouTubeAPIService()
        except Exception as e:
            print(f"ℹ️ YouTube API not available: {e}")
        
        # Проверяем переменную окружения для Railway деплоя
        import base64
        cookies_env = os.getenv('YOUTUBE_COOKIES_BASE64')
        if cookies_env:
            try:
                # Убираем всё, что не похоже на Base64
                import re
                cookies_env = re.sub(r'[^A-Za-z0-9+/=]', '', cookies_env).strip()
                
                # Ищем начало Netscape файла (Base64 для '# ' это 'IyB')
                if 'IyB' in cookies_env:
                    cookies_env = cookies_env[cookies_env.find('IyB'):]
                
                # Убираем ведущие '=', они могут появиться при неправильном копировании
                cookies_env = cookies_env.lstrip('=')
                
                # Добавляем недостающий padding (Base64 требует кратность 4)
                missing_padding = len(cookies_env) % 4
                if missing_padding:
                    cookies_env += '=' * (4 - missing_padding)
                
                print(f"📦 Attempting to restore YouTube cookies...")
                try:
                    cookies_bytes = base64.b64decode(cookies_env)
                    try:
                        cookies_content = cookies_bytes.decode('utf-8')
                    except UnicodeDecodeError:
                        cookies_content = cookies_bytes.decode('latin-1')
                except Exception as b64e:
                    print(f"❌ Base64 decoding failed: {b64e}")
                    raise b64e
                
                # Диагностика: проверим формат
                is_netscape = '# Netscape' in cookies_content[:100] or '# HTTP' in cookies_content[:100]
                
                if len(cookies_content) > 10:
                    preview = cookies_content[:30].replace('\n', ' ')
                    print(f"📊 Decoded cookie content preview: {preview}...")
                    print(f"📏 Decoded size: {len(cookies_content)} bytes")
                    if not is_netscape:
                        print(f"⚠️ WARNING: Cookies do NOT look like Netscape format! Download might fail.")
                    else:
                        print(f"✅ Cookie format looks valid (Netscape)")
                
                with open(self.cookies_path, 'w', encoding='utf-8') as f:
                    f.write(cookies_content)
                print(f"✅ YouTube cookies restored/updated to: {self.cookies_path}")
            except Exception as e:
                print(f"❌ Failed to restore cookies from environment: {e}")
                import traceback
                traceback.print_exc()
        
        if os.path.exists(self.cookies_path):
            print(f"🍪 YouTube cookie file found: {self.cookies_path}")
        else:
            if not self.youtube_api or not self.youtube_api.api_key:
                print(f"⚠️ YouTube cookie file NOT found at: {self.cookies_path}")
                print(f"   Set YOUTUBE_API_KEY or YOUTUBE_COOKIES_BASE64 environment variable")
            else:
                print(f"✅ Using YouTube API instead of cookies")
        
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
        
        # Если доступен YouTube API, используем его для поиска
        youtube_url = None
        if self.youtube_api and self.youtube_api.api_key:
            print(f"🔍 Searching via YouTube API: {search_query}")
            video_info = self.youtube_api.search_video(search_query)
            if video_info:
                youtube_url = video_info['url']
                print(f"✅ Found via API: {video_info['title']}")
            else:
                print(f"⚠️ API search failed, falling back to yt-dlp search")
        
        # Модифицируем шаблон имени файла чтобы избежать коллизий качества
        safe_name = "".join([c if c.isalnum() or c in " -_" else "_" for c in f"{artist} - {track_name}"])
        out_tmpl = os.path.join(self.download_dir, f"{safe_name}_{quality}.%(ext)s")
        
        ydl_opts = {
            'format': 'bestaudio/best', # Первый этап: стандартное аудио
            'outtmpl': out_tmpl,
            'overwrites': True,
            'cachedir': False,
            'source_address': '0.0.0.0', # Принудительно IPv4 для Railway
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
            'default_search': 'ytsearch1' if not youtube_url else None,
            'extractor_args': {
                'youtube': {
                    'player_client': ['mweb', 'web_music', 'android', 'ios'],
                    'skip': ['translated_subs'],
                    'po_token': 'mweb',
                }
            },
            'referer': 'https://www.google.com/',
            'noproxy': True,
            'socket_timeout': 30,
            'retries': 5,
            'geo_bypass': True,
            'nocheckcertificate': True,
            'age_limit': 99,
            'cookiefile': self.cookies_path if os.path.exists(self.cookies_path) else None,
        }
        
        download_target = youtube_url if youtube_url else search_query
        loop = asyncio.get_event_loop()
        
        try:
            # Попытка 1: Стандартное лучшее аудио
            print(f"🚀 Download Attempt 1 (ba/best): {search_query}")
            result = await loop.run_in_executor(None, self._download_sync, download_target, ydl_opts, file_format)
            
            # Если ошибка формата или блокировка
            if result and isinstance(result, dict) and 'error' in result:
                err_msg = result['error']
                if "format is not available" in err_msg or "bot" in err_msg or "403" in err_msg:
                    print(f"⚠️ Attempt 1 failed. Triggering Attempt 2 (ba*/b* + Mobile only)...")
                    
                    # Попытка 2: Расширенный поиск аудио/видео + только мобильные
                    ydl_opts['format'] = 'ba*/b*' 
                    ydl_opts['extractor_args']['youtube']['player_client'] = ['android', 'ios']
                    
                    # Маленькая задержка перед ретраем
                    await asyncio.sleep(1)
                    result = await loop.run_in_executor(None, self._download_sync, download_target, ydl_opts, file_format)
                    
                    # Если всё ещё ошибка - Попытка 3: Универсальный захват
                    if result and isinstance(result, dict) and 'error' in result:
                        print(f"⚠️ Attempt 2 failed. FINAL ATTEMPT 3 (* + TV/Embedded)...")
                        ydl_opts['format'] = '*' # Берем ВООБЩЕ любой доступный поток
                        ydl_opts['extractor_args']['youtube']['player_client'] = ['web_embedded', 'tv']
                        
                        await asyncio.sleep(1)
                        result = await loop.run_in_executor(None, self._download_sync, download_target, ydl_opts, file_format)
            
            return result
        except Exception as e:
            print(f"❌ Ошибка скачивания {search_query}: {e}")
            return {'error': str(e)}
    
    async def get_metadata_only(self, artist: str, track_name: str) -> Optional[Dict]:
        """
        Только поиск метаданных (без скачивания)
        """
        search_query = f"{artist} - {track_name}"
        
        # Приоритет: YouTube API (быстрее и надежнее)
        if self.youtube_api and self.youtube_api.api_key:
            try:
                video_info = self.youtube_api.search_video(search_query)
                if video_info:
                    return {
                        'thumbnail': video_info.get('thumbnail'),
                        'title': video_info.get('title'),
                        'duration': None  # API не возвращает duration в search
                    }
            except Exception as e:
                print(f"⚠️ YouTube API metadata search failed: {e}")
        
        # Fallback: yt-dlp (если API недоступен или не сработал)
        import yt_dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch1',
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios', 'android', 'web_music'],
                    'skip': ['translated_subs'],
                }
            },
            'referer': 'https://www.google.com/',
            'noproxy': True,
            'cookiefile': self.cookies_path if os.path.exists(self.cookies_path) else None,
        }
        
        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, self._extract_info_sync, search_query, ydl_opts)
            if info and 'entries' in info and info['entries']:
                entry = info['entries'][0]
                return {
                    'thumbnail': entry.get('thumbnail'),
                    'title': entry.get('title'),
                    'duration': entry.get('duration')
                }
            return None
        except Exception as e:
            print(f"❌ Metadata search error for {search_query}: {e}")
            return None

    def _extract_info_sync(self, query: str, opts: dict):
        import yt_dlp
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(query, download=False)

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
            return {'error': str(e)}

    
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
            # Обход блокировки YouTube "Sign in to confirm you're not a bot"
            # Удаляем жесткий user_agent для автоматического подбора под клиента
            'extractor_args': {
                'youtube': {
                    'player_client': ['android'],
                    'skip': ['hls', 'dash', 'translated_subs'],
                    'include_dash_manifest': False,
                    'include_hls_manifest': False,
                }
            },
            'socket_timeout': 30,
            'retries': 5,
            'geo_bypass': True,
            'nocheckcertificate': True,
            'age_limit': 99,  # Обход возрастных ограничений
            'cookiefile': self.cookies_path if os.path.exists(self.cookies_path) else None,
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
            return {'error': str(e)}
    
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
