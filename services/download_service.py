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
                    
                    # Санитайзер кук: приводим к стандарту Netscape
                    cookies_content = self._sanitize_cookies(cookies_content)
                    
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
                print(f"✅ YouTube cookies restored and sanitized to {self.cookies_path}")
            except Exception as e:
                print(f"⚠️ Failed to restore YouTube cookies: {e}")
                import traceback
                traceback.print_exc()
        
        # Диагностика окружения для 2026 года (SABR / n-challenge)
        self._check_environment()

    def _check_environment(self):
        """Проверка наличия JS Runtime для решения n-challenge"""
        try:
            import subprocess
            node_version = subprocess.check_output(['node', '-v'], stderr=subprocess.STDOUT).decode().strip()
            print(f"✅ [2026 Environment] Node.js detected: {node_version}")
            
            # Проверка yt-dlp версии
            import yt_dlp
            print(f"✅ [2026 Environment] yt-dlp version: {yt_dlp.version.__version__}")
            
            # Check ffmpeg
            try:
                ffmpeg_version = subprocess.check_output(['ffmpeg', '-version'], stderr=subprocess.STDOUT).decode().splitlines()[0]
                print(f"✅ [2026 Environment] ffmpeg detected: {ffmpeg_version}")
            except FileNotFoundError:
                print(f"⚠️ [2026 Environment] ffmpeg NOT found! Conversions to MP3 will fail.")
                
        except Exception as e:
            print(f"⚠️ [2026 Environment] Diagnostic warning: {e}")
            print(f"ℹ️ YouTube downloads might fail without a JS runtime on some tracks.")

    def _sanitize_cookies(self, content: str) -> str:
        """Очистка и исправление формата кук Netscape"""
        lines = content.splitlines()
        sanitized = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith('#'):
                sanitized.append(line)
                continue
            
            # Убираем невидимые символы и ESC-последовательности
            line = "".join(ch for ch in line if ch.isprintable() or ch == '\t')
            
            parts = line.split('\t')
            if len(parts) >= 7:
                # Берем только первые 7 колонок, если их больше
                sanitized.append("\t".join(parts[:7]))
            elif len(parts) > 1:
                # Если колонок не хватает, пробуем дополнить пустыми (хотя это риск)
                while len(parts) < 7:
                    parts.append('')
                sanitized.append("\t".join(parts))
        
        # Гарантируем заголовок Netscape
        if sanitized and not sanitized[0].startswith('# Netscape'):
            sanitized.insert(0, '# Netscape HTTP Cookie File')
            sanitized.insert(1, '# This file is generated by DownloadService sanitizer')
            
        return "\n".join(sanitized) + "\n"

    def _check_environment(self):
        print(f"🚀 DownloadService v13 (Robust File Resolution) Loaded")
        if os.path.exists(self.cookies_path):
            print(f"🍪 YouTube cookie file found: {self.cookies_path}")
        else:
            if not self.youtube_api or not self.youtube_api.api_key:
                print(f"⚠️ YouTube cookie file NOT found at: {self.cookies_path}")
                print(f"   Set YOUTUBE_API_KEY or YOUTUBE_COOKIES_BASE64 environment variable")
            else:
                print(f"✅ Using YouTube API instead of cookies")
        
    def _extract_youtube_id(self, error_msg: str) -> Optional[str]:
        """Извлечение YouTube ID из сообщения об ошибке"""
        import re
        match = re.search(r'\[youtube\] ([a-zA-Z0-9_-]{11}):', error_msg)
        if match:
            return match.group(1)
        return None

    def _create_blacklist_filter(self, failed_id: str):
        """Создает фильтр для блокировки конкретного ID"""
        def match_filter(info_dict, incomplete=False):
            if info_dict.get('id') == failed_id:
                return f"Video ID {failed_id} is blacklisted"
            return None
        return match_filter

    def _resolve_downloaded_file(self, ydl, info, file_format, download_dir):
        """Logic to finding the downloaded file on disk"""
        import glob
        import time

        # Handle Search Results / Playlist
        entries = [info]
        if 'entries' in info:
            entries = [e for e in info['entries'] if e] # Filter None entries (from ignoreerrors=True)

        # Check each entry to see if its file exists
        for i, entry in enumerate(entries):
            # 1. Predict 
            base_path = ydl.prepare_filename(entry)
            file_path = os.path.splitext(base_path)[0] + f'.{file_format}'
            
            print(f"🔍 Checking entry {i} ({entry.get('id')}): {file_path}")
            
            if os.path.exists(file_path):
                print(f"✅ Found file at: {file_path}")
                return file_path, entry
            
            # 2. Check metadata
            actual_filename = entry.get('_filename')
            if actual_filename:
                potential_path = os.path.splitext(actual_filename)[0] + f'.{file_format}'
                if os.path.exists(potential_path):
                    print(f"✅ Found file via metadata match: {potential_path}")
                    return potential_path, entry

        print("⚠️ No direct match found in entries. Checking recent files (Universal Fallback)...")
        # 3. Fallback: Recent file (Universal - ignores extension/name matches)
        # Scan for ANY file type that might have been downloaded (mp3, webm, m4a, opus)
        possible_extensions = [file_format, 'webm', 'm4a', 'opus', 'mp4']
        recent_candidates = []
        
        now = time.time()
        for ext in possible_extensions:
            pattern = os.path.join(download_dir, f'*.{ext}')
            files = glob.glob(pattern)
            recent_candidates.extend([f for f in files if now - os.path.getctime(f) < 60])
            
        if recent_candidates:
            # Pick the most recent one
            best_candidate = max(recent_candidates, key=os.path.getctime)
            print(f"✅ Found file via Universal Fallback: {best_candidate}")
            return best_candidate, entries[0] if entries else info
            
        print("❌ All search results failed or no file written to disk.")
        return None, info

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
                    'player_client': ['android', 'ios'],
                    'skip': ['translated_subs'],
                    'include_dash_manifest': True,
                    'include_hls_manifest': True,
                }
            },
            'format_sort': ['acodec:opus', 'res', 'lang', 'quality'],
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
            # Попытка 1: February 2026 Mobile Attempt
            print(f"🚀 Download Attempt 1 (Stable Mobile 2026): {download_target}")
            result = await loop.run_in_executor(None, self._download_sync, download_target, ydl_opts, file_format)
            
            # Если ошибка формата или блокировка
            if result and isinstance(result, dict) and 'error' in result:
                err_msg = result['error']
                failed_id = self._extract_youtube_id(err_msg)
                is_unavailable = any(term in err_msg for term in ["format is not available", "bot", "Sign in", "403", "Video unavailable"])
                
                if is_unavailable:
                    # Черный список: если ID сдох, принудительно исключаем его из поиска
                    if failed_id:
                        print(f"🚫 Blacklisting failing ID {failed_id} and retrying alternative search...")
                        ydl_opts['match_filter'] = self._create_blacklist_filter(failed_id)
                    
                    if youtube_url or failed_id:
                        youtube_url = None
                        download_target = search_query 
                        ydl_opts['default_search'] = 'ytsearch5' # Берем 5 вариантов
                        ydl_opts['noplaylist'] = False # Разрешаем перебор плейлиста поиска
                        ydl_opts['max_downloads'] = 1 # Качаем только 1 успешный трек
                        ydl_opts['ignoreerrors'] = True # v10: Игнорируем ошибки (Sign in) для пропуска битых треков в поиске
                        # v12: Уникальные имена файлов для каждого кандидата в поиске
                        safe_query = "".join([c if c.isalnum() or c in " -_" else "_" for c in search_query])
                        ydl_opts['outtmpl'] = os.path.join(self.download_dir, f"{safe_query}_%(id)s_{quality}.%(ext)s")
                    
                    # Попытка 2: Переход на Music Web (для клипов)
                    print(f"⚠️ Attempt 1 failed. Triggering Attempt 2 (Music Web Mode + Blacklist)...")
                    ydl_opts['extractor_args']['youtube']['player_client'] = ['web_music', 'mweb', 'android']
                    
                    await asyncio.sleep(2)
                    result = await loop.run_in_executor(None, self._download_sync, download_target, ydl_opts, file_format)
                    
                    # Попытка 3: TV-клиенты (последний рубеж против SABR)
                    if result and isinstance(result, dict) and 'error' in result:
                        print(f"⚠️ Attempt 2 failed. Triggering Attempt 3 (TV Capture)...")
                        ydl_opts['format'] = '*' 
                        ydl_opts['extractor_args']['youtube']['player_client'] = ['tv', 'web_embedded']
                        
                        await asyncio.sleep(2)
                        result = await loop.run_in_executor(None, self._download_sync, download_target, ydl_opts, file_format)
                    
                    # Попытка 4 (Nuclear): Гостевой режим БЕЗ КУКОВ
                    if result and isinstance(result, dict) and 'error' in result:
                        print(f"⚠️ Attempt 3 failed. NUCLEAR ATTEMPT 4 (Guest Mode - No Cookies)...")
                        ydl_opts['format'] = '*'
                        ydl_opts['cookiefile'] = None
                        ydl_opts['extractor_args']['youtube']['player_client'] = ['web_embedded', 'mweb']
                        
                        await asyncio.sleep(2)
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
                    
                file_path, valid_entry = self._resolve_downloaded_file(ydl, info, file_format, self.download_dir)
                
                # Update info with the actual track data
                if valid_entry:
                    info = valid_entry

                title = info.get('title', 'Unknown')
                duration = info.get('duration', 0)
                
                # Final verification
                file_size = 0
                if file_path and os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                else:
                    print(f"⚠️ Файл не найден после всех попыток: {file_path}")
                    # Last ditch effort
                    import glob
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
        # v13: Ограничиваем длину имени файла до 50 символов чтобы избежать OS Error
        safe_query = "".join([c if c.isalnum() or c in " -_" else "_" for c in search_query])[:50]
        out_tmpl = os.path.join(self.download_dir, f"{safe_query}_{quality}.%(ext)s")
        
        ydl_opts = {
            'format': 'bestaudio/best', # Этап 1: Стандартное аудио
            'outtmpl': out_tmpl,
            'overwrites': True,
            'cachedir': False,
            'source_address': '0.0.0.0', # Принудительно IPv4 для Railway
            'noplaylist': True,
            'ignore_no_formats_error': True,
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
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios'],
                    'skip': ['translated_subs'],
                    'include_dash_manifest': True,
                    'include_hls_manifest': True,
                }
            },
            'format_sort': ['acodec:opus', 'res', 'lang', 'quality'],
            'referer': 'https://www.google.com/',
            'noproxy': True,
            'socket_timeout': 30,
            'retries': 5,
            'geo_bypass': True,
            'nocheckcertificate': True,
            'age_limit': 99,
            'cookiefile': self.cookies_path if os.path.exists(self.cookies_path) else None,
        }
        
        loop = asyncio.get_event_loop()
        
        try:
            # Попытка 1: February 2026 Mobile Attempt
            print(f"🚀 Query Download Attempt 1 (Stable Mobile 2026): {search_query}")
            result = await loop.run_in_executor(None, self._download_sync, search_query, ydl_opts, file_format)
            
            # Если ошибка формата или блокировка
            if result and isinstance(result, dict) and 'error' in result:
                err_msg = result['error']
                failed_id = self._extract_youtube_id(err_msg)
                is_unavailable = any(term in err_msg for term in ["format is not available", "bot", "Sign in", "403", "Video unavailable"])

                if is_unavailable:
                    if failed_id:
                        print(f"🚫 Blacklisting query ID {failed_id} and retrying alternative search...")
                        ydl_opts['match_filter'] = self._create_blacklist_filter(failed_id)
                        ydl_opts['default_search'] = 'ytsearch5'
                        ydl_opts['noplaylist'] = False
                        ydl_opts['max_downloads'] = 1
                        ydl_opts['ignoreerrors'] = True # v10: Игнорируем ошибки (Sign in) для пропуска битых треков в поиске
                        # v12: Уникальные имена файлов для каждого кандидата в поиске
                        # v13: Truncate safe_query
                        ydl_opts['outtmpl'] = os.path.join(self.download_dir, f"{safe_query}_%(id)s_{quality}.%(ext)s")

                    # Попытка 2: Переход на Music Web (для клипов)
                    print(f"⚠️ Query Attempt 1 failed. Triggering Attempt 2 (Music Web Mode + Blacklist)...")
                    ydl_opts['extractor_args']['youtube']['player_client'] = ['web_music', 'mweb', 'android']
                    
                    await asyncio.sleep(2)
                    result = await loop.run_in_executor(None, self._download_sync, search_query, ydl_opts, file_format)
                    
                    # Попытка 3: TV-клиенты (последний рубеж против SABR)
                    if result and isinstance(result, dict) and 'error' in result:
                        print(f"⚠️ Query Attempt 2 failed. Triggering Attempt 3 (TV Capture)...")
                        ydl_opts['format'] = '*' 
                        ydl_opts['extractor_args']['youtube']['player_client'] = ['tv', 'web_embedded']
                        
                        await asyncio.sleep(2)
                        result = await loop.run_in_executor(None, self._download_sync, search_query, ydl_opts, file_format)
                    
                    # Попытка 4 (Nuclear): Гостевой режим БЕЗ КУКОВ
                    if result and isinstance(result, dict) and 'error' in result:
                        print(f"⚠️ Query Attempt 3 failed. NUCLEAR ATTEMPT 4 (Guest Mode - No Cookies)...")
                        ydl_opts['format'] = '*'
                        ydl_opts['cookiefile'] = None
                        ydl_opts['extractor_args']['youtube']['player_client'] = ['web_embedded', 'mweb']
                        
                        await asyncio.sleep(2)
                        result = await loop.run_in_executor(None, self._download_sync, search_query, ydl_opts, file_format)
            
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
