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
        """Проверка окружения и диагностика (v15)"""
        print(f"🚀 DownloadService v15 (Unconditional Fallback) Loaded")
        print(f"📂 Download directory: {self.download_dir}")
        print(f"📍 Current Workdir: {os.getcwd()}")
        
        try:
            import subprocess
            # Check Node.js
            try:
                node_version = subprocess.check_output(['node', '-v'], stderr=subprocess.STDOUT).decode().strip()
                print(f"✅ [2026] Node.js detected: {node_version}")
            except Exception:
                print(f"⚠️ [2026] Node.js NOT found! YouTube might fail n-challenge.")

            # Check yt-dlp
            print(f"✅ [2026] yt-dlp version: {yt_dlp.version.__version__}")
            
            # Check ffmpeg
            try:
                ffmpeg_output = subprocess.check_output(['ffmpeg', '-version'], stderr=subprocess.STDOUT).decode().splitlines()[0]
                print(f"✅ [2026] ffmpeg detected: {ffmpeg_output}")
            except Exception:
                print(f"⚠️ [2026] ffmpeg NOT found! Conversions to MP3 will fail.")
                
            # Check cookies
            if os.path.exists(self.cookies_path):
                print(f"🍪 YouTube cookie file found: {self.cookies_path}")
            else:
                if not self.youtube_api or not self.youtube_api.api_key:
                    print(f"⚠️ YouTube cookie file NOT found at: {self.cookies_path}")
                else:
                    print(f"✅ Using YouTube API instead of cookies")
                    
        except Exception as e:
            print(f"⚠️ Diagnostic error: {e}")

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

    def _is_error_fatal(self, result):
        """Check if result is a success or if we should skip fallback"""
        if not result: return False
        if not isinstance(result, dict): return True
        if 'error' in result: return False
        if not result.get('file_path') or not os.path.exists(result['file_path']): return False
        return True # Success
        
    def _extract_youtube_id(self, error_msg: str) -> Optional[str]:
        """Извлечение YouTube ID из сообщения об ошибке"""
        if not error_msg or not isinstance(error_msg, str):
            return None
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
        if not info: return None, None
        
        entries = info.get('entries', [info])
        entries = [e for e in entries if e] # Filter None entries (from ignoreerrors=True)

        if not entries:
            print("⚠️ No valid entries found in results.")
            return None, info

        # Check each entry to see if its file exists
        for i, entry in enumerate(entries):
            # 1. Predict filename via yt-dlp logic
            try:
                base_path = ydl.prepare_filename(entry)
                file_path = os.path.splitext(base_path)[0] + f'.{file_format}'
                
                print(f"🔍 Entry {i} ({entry.get('id')}): Checking {file_path}")
                
                if os.path.exists(file_path):
                    print(f"✅ Found file at: {file_path}")
                    return file_path, entry
            except Exception as e:
                print(f"⚠️ Error preparing filename: {e}")
            
            # 2. Check metadata fallback
            actual_filename = entry.get('_filename')
            if actual_filename:
                potential_path = os.path.splitext(actual_filename)[0] + f'.{file_format}'
                if os.path.exists(potential_path):
                    print(f"✅ Found file via metadata match: {potential_path}")
                    return potential_path, entry

        print("⚠️ No direct match. Checking variants (Universal Fallback v15)...")
        # 3. Fallback: Search by ID (if ID is in filename)
        for entry in entries:
            vid_id = entry.get('id')
            if vid_id:
                print(f"🔍 Look for ID: *{vid_id}*")
                pattern = os.path.join(download_dir, f'*{vid_id}*.*')
                id_files = [f for f in glob.glob(pattern) if not f.endswith('.part') and not f.endswith('.ytdl')]
                if id_files:
                    best_id_file = max(id_files, key=os.path.getmtime)
                    print(f"✅ Found file via ID match: {best_id_file}")
                    return best_id_file, entry

        # 4. Fallback: Recent file (Universal)
        possible_extensions = [file_format, 'webm', 'm4a', 'opus', 'mp4', 'mkv', 'mp3']
        recent_candidates = []
        
        now = time.time()
        for ext in possible_extensions:
            pattern = os.path.join(download_dir, f'*.{ext}')
            for f in glob.glob(pattern):
                # Window: 5 minutes (300s)
                if now - os.path.getmtime(f) < 300:
                    recent_candidates.append(f)
            
        if recent_candidates:
            best_candidate = max(recent_candidates, key=os.path.getmtime)
            print(f"✅ Found file via Recent Fallback: {best_candidate}")
            return best_candidate, entries[0]
            
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
            # v15: Unconditional Fallback Chain
            strategies = [
                # 1. Mobile (Standard)
                {"player_client": ["android", "ios"]},
                # 2. Music Web (Music specific)
                {"player_client": ["web_music", "mweb", "android"]},
                # 3. TV (Legacy / SABR fix)
                {"player_client": ["tv", "web_embedded"]},
                # 4. Nuclear (No Cookies)
                {"player_client": ["web_embedded", "mweb"], "no_cookies": True}
            ]
            
            last_result = None
            for i, strategy in enumerate(strategies, 1):
                current_opts = ydl_opts.copy()
                current_opts['extractor_args'] = {'youtube': {k: v for k, v in strategy.items() if k != 'no_cookies'}}
                
                if strategy.get('no_cookies'):
                    current_opts['cookiefile'] = None
                
                # If we already failed once, switch target to BROAD SEARCH for alternatives
                if i > 1:
                    if download_target != search_query:
                        print(f"🔄 Switching from direct URL to search fallback: {search_query}")
                        download_target = search_query

                    current_opts['default_search'] = 'ytsearch5'
                    current_opts['noplaylist'] = False
                    current_opts['max_downloads'] = 1
                    current_opts['ignoreerrors'] = True
                    safe_query = "".join([c if c.isalnum() or c in " -_" else "_" for c in search_query])
                    current_opts['outtmpl'] = os.path.join(self.download_dir, f"{safe_query}_%(id)s_{quality}.%(ext)s")

                # v17: Broaden format if audio-only fails (TV & Nuclear steps)
                if i >= 3:
                    print(f"☢️ Step {i}: Enabling broad format fallback ('*')")
                    current_opts['format'] = '*'

                print(f"📡 Strategy {i}/4: Trying {strategy}")
                last_result = await loop.run_in_executor(None, self._download_sync, download_target, current_opts, file_format)
                
                if self._is_error_fatal(last_result):
                    print(f"✨ Step {i} SUCCEEDED!")
                    return last_result
                
                # Extract error string safely (v17 crash fix)
                err_str = last_result.get('error') if isinstance(last_result, dict) else str(last_result)
                if not err_str or err_str == 'None': err_str = "Unknown download failure"
                
                print(f"❌ Step {i} failed. Reason: {err_str}")
                
                # If we have a failed ID, blacklist it for next attempts
                failed_id = self._extract_youtube_id(err_str)
                if failed_id:
                    print(f"🚫 Blacklisting ID {failed_id} for next steps")
                    ydl_opts['match_filter'] = self._create_blacklist_filter(failed_id)
                
                await asyncio.sleep(1)

            return last_result
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
                    # Last ditch effort: ANY file in downloads
                    import glob
                    files = []
                    for ext in [file_format, 'webm', 'm4a', 'opus', 'mp4']:
                        pattern = os.path.join(self.download_dir, f'*.{ext}')
                        files.extend(glob.glob(pattern))
                    
                    if files:
                        file_path = max(files, key=os.path.getmtime)
                        file_size = os.path.getsize(file_path)
                        print(f"🆘 Emergency recovery: Using {file_path}")

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
            # v15: Unconditional Fallback Chain for Queries
            strategies = [
                {"player_client": ["android", "ios"]},
                {"player_client": ["web_music", "mweb", "android"]},
                {"player_client": ["tv", "web_embedded"]},
                {"player_client": ["web_embedded", "mweb"], "no_cookies": True}
            ]
            
            last_result = None
            for i, strategy in enumerate(strategies, 1):
                current_opts = ydl_opts.copy()
                current_opts['extractor_args'] = {'youtube': {k: v for k, v in strategy.items() if k != 'no_cookies'}}
                
                if strategy.get('no_cookies'):
                    current_opts['cookiefile'] = None
                
                if i > 1:
                    current_opts['default_search'] = 'ytsearch5'
                    current_opts['noplaylist'] = False
                    current_opts['max_downloads'] = 1
                    current_opts['ignoreerrors'] = True
                    current_opts['outtmpl'] = os.path.join(self.download_dir, f"{safe_query}_%(id)s_{quality}.%(ext)s")

                # v17: Broaden format for query fallback too
                if i >= 3:
                    current_opts['format'] = '*'

                print(f"📡 Query Step {i}/4: Trying strategy {strategy}")
                last_result = await loop.run_in_executor(None, self._download_sync, search_query, current_opts, file_format)
                
                if self._is_error_fatal(last_result):
                    print(f"✨ Query Strategy {i} SUCCEEDED!")
                    return last_result
                
                # Safe error extraction
                err_str = last_result.get('error') if isinstance(last_result, dict) else str(last_result)
                if not err_str or err_str == 'None': err_str = "Unknown query failure"
                
                if isinstance(last_result, dict) and 'error' in last_result:
                    failed_id = self._extract_youtube_id(err_str)
                    if failed_id:
                        ydl_opts['match_filter'] = self._create_blacklist_filter(failed_id)
                
                await asyncio.sleep(1)

            return last_result
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
