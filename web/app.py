"""
Flask Web Application для музыкального бота
"""
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import asyncio
import os
import sys

# Добавляем корневую директорию в путь для импорта модулей
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from services.spotify_service import SpotifyService
from services.download_service import DownloadService
from database.db_manager import DatabaseManager

app = Flask(__name__)
CORS(app)

# Инициализация сервисов
spotify_service = SpotifyService()
download_service = DownloadService()
db = DatabaseManager()

# Telegram Storage Service будет инициализирован при первом использовании
telegram_storage = None
backup_service = None

def get_telegram_storage():
    """Ленивая инициализация Telegram Storage Service"""
    global telegram_storage
    if telegram_storage is None:
        from services.telegram_storage_service import TelegramStorageService
        telegram_storage = TelegramStorageService()
    return telegram_storage

def get_backup_service():
    """Ленивая инициализация Database Backup Service"""
    global backup_service
    if backup_service is None:
        from services.db_backup_service import DatabaseBackupService
        backup_service = DatabaseBackupService(
            storage_service=get_telegram_storage(),
            db_path=config.DATABASE_URL.replace('sqlite+aiosqlite:///', '')
        )
    return backup_service

# Флаг инициализации БД
db_initialized = False

def ensure_db_initialized():
    """Ленивая инициализация БД при первом запросе с восстановлением из Telegram"""
    global db_initialized
    if not db_initialized:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            print("📦 Web App: Checking for database restoration...")
            # Попытка восстановления из Telegram перед инициализацией
            backup = get_backup_service()
            loop.run_until_complete(backup.restore_from_telegram())
            
            # Инициализация (создание таблиц, если не созданы)
            loop.run_until_complete(db.init_db())
            loop.close()
            db_initialized = True
            print("✅ Web App: Database ready")
        except Exception as e:
            print(f"⚠️  Web App: Database init warning: {e}")
            import traceback
            traceback.print_exc()
            db_initialized = True # Помечаем как инициализированную, чтобы не входить в цикл при ошибках

@app.before_request
def before_request():
    """Инициализация БД перед первым запросом"""
    ensure_db_initialized()

@app.route('/health')
def health_check():
    return jsonify({'status': 'ok'}), 200

@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')

@app.route('/api/search', methods=['POST'])
def search():
    """Поиск треков"""
    try:
        data = request.json
        query = data.get('query', '')
        
        if not query:
            return jsonify({'error': 'Query is required'}), 400
        
        # Проверяем, является ли query Spotify URL
        if 'spotify.com' in query or 'open.spotify' in query:
            return search_by_url(query)
        
        # Обычный поиск по тексту
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(spotify_service.search_track(query))
        loop.close()
        
        if not results:
            return jsonify({'tracks': []})
        
        # Форматируем результаты
        tracks = []
        for track in results[:10]:
            tracks.append({
                'id': track.get('id'),
                'name': track.get('name'),
                'artist': track.get('artist'),
                'album': track.get('album'),
                'duration': track.get('duration_ms', 0) // 1000,
                'image': track.get('image_url'),
                'preview_url': track.get('preview_url')
            })
        
        return jsonify({'tracks': tracks})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/library', methods=['GET'])
def get_library():
    """Получить все треки из библиотеки (кэша)"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        tracks_db = loop.run_until_complete(db.get_library_tracks(limit=1000))
        loop.close()
        
        tracks = []
        for track in tracks_db:
            tracks.append({
                'id': track.id,
                'name': track.name,
                'artist': track.artist,
                'album': track.album,
                'image': track.image_url,
                'spotify_url': track.spotify_url
            })
            
        return jsonify({'tracks': tracks})
        
    except Exception as e:
        print(f"❌ Error in get_library: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sync-library', methods=['POST'])
def sync_library():
    """Синхронизировать библиотеку с Telegram-каналом"""
    try:
        # Проверяем авторизацию (опционально, но желательно)
        # auth_header = request.headers.get('Authorization')
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 1. Сканируем канал
        storage = get_telegram_storage()
        tracks = loop.run_until_complete(storage.scan_channel_audio(limit=200)) # Сканируем последние 200 сообщений
        
        # 2. Сохраняем новые треки в БД
        new_count = 0
        for track in tracks:
            is_new = loop.run_until_complete(db.sync_telegram_track(track))
            if is_new:
                new_count += 1
        
        loop.close()
        
        return jsonify({
            'success': True,
            'new_tracks_found': new_count,
            'total_scanned': len(tracks)
        })
        
    except Exception as e:
        print(f"❌ Error in sync_library: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def search_by_url(url):
    """Поиск по Spotify URL"""
    try:
        # Определяем тип URL (track, album, playlist)
        if '/track/' in url:
            # Получаем информацию о треке (синхронный метод)
            track_info = spotify_service.get_track_info_from_url(url)
            
            if track_info:
                return jsonify({
                    'tracks': [{
                        'id': track_info.get('id', ''),
                        'name': track_info.get('name'),
                        'artist': track_info.get('artist'),
                        'album': track_info.get('album', ''),
                        'duration': 0,
                        'image': track_info.get('image_url'),
                        'preview_url': None
                    }]
                })
        
        elif '/album/' in url or '/playlist/' in url:
            # Для альбомов и плейлистов пока не поддерживается
            return jsonify({
                'error': 'Album and playlist support coming soon',
                'tracks': []
            })
        
        return jsonify({'tracks': []})
    
    except Exception as e:
        print(f"❌ Error in search_by_url: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'tracks': []})

@app.route('/api/download', methods=['POST'])
def download():
    """Скачивание трека"""
    try:
        data = request.json
        track_id = data.get('track_id')
        track_name = data.get('track_name')
        track_artist = data.get('track_artist')
        quality = data.get('quality', '320')
        file_format = data.get('format', 'mp3')
        
        # Если есть имя и исполнитель, используем их напрямую
        if track_name and track_artist:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            result = loop.run_until_complete(
                download_service.search_and_download(
                    track_artist,
                    track_name,
                    quality,
                    file_format
                )
            )
            loop.close()
            
            if result and result.get('file_path') and os.path.exists(result['file_path']):
                file_path = result['file_path']
                return send_file(
                    file_path,
                    as_attachment=True,
                    download_name=f"{track_artist} - {track_name}.{file_format}"
                )
            else:
                error_msg = result.get('error') if result else "Unknown error"
                return jsonify({'error': f"Download failed: {error_msg}"}), 500
        
        # Иначе используем track_id
        if not track_id:
            return jsonify({'error': 'Track ID or name/artist is required'}), 400
        
        # Скачивание трека по ID
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Получаем информацию о треке
        track_info = loop.run_until_complete(spotify_service.get_track_info(track_id))
        
        if not track_info:
            return jsonify({'error': 'Track not found'}), 404
        
        # Скачиваем трек
        result = loop.run_until_complete(
            download_service.search_and_download(
                track_info['artist'],
                track_info['name'],
                quality,
                file_format
            )
        )
        loop.close()
        
        if result and result.get('file_path') and os.path.exists(result['file_path']):
            file_path = result['file_path']
            return send_file(
                file_path,
                as_attachment=True,
                download_name=f"{track_info['artist']} - {track_info['name']}.{file_format}"
            )
        else:
            error_msg = result.get('error') if result else "Unknown error"
            return jsonify({'error': f"Download failed: {error_msg}"}), 500
    
    except Exception as e:
        print(f"❌ Download error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# Временное хранилище токенов (в идеале использовать Redis или общую таблицу в БД)
# Но для простоты пока будем использовать глобальную переменную, 
# так как бот и веб работают в разных процессах, нам нужно общее хранилище.
# ОБНОВЛЕНИЕ: Лучше использовать таблицу в БД для синхронизации между процессами.

@app.route('/api/auth', methods=['POST'])
def authenticate():
    """Верификация токена из Telegram"""
    try:
        data = request.json
        token = data.get('token')
        
        if not token:
            return jsonify({'error': 'Token is required'}), 400
            
        # Проверяем токен в БД
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        user = loop.run_until_complete(db.verify_auth_token(token))
        loop.close()
        
        if user:
            return jsonify({
                'success': True,
                'user': {
                    'id': user.id,
                    'username': user.username or 'User',
                    'first_name': user.first_name,
                    'last_name': user.last_name
                }
            })
        else:
            return jsonify({'error': 'Invalid or expired token'}), 401
    except Exception as e:
        print(f"❌ Auth error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/playlists', methods=['GET', 'POST'])
def handle_playlists():
    """Работа с плейлистами"""
    try:
        user_id = request.headers.get('X-User-ID')
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
            
        user_id = int(user_id)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
            
        if request.method == 'GET':
            # Получить список плейлистов
            playlists_db = loop.run_until_complete(db.get_user_playlists(user_id))
            
            result = []
            for pl in playlists_db:
                # Получаем количество треков
                count = loop.run_until_complete(db.get_playlist_track_count(pl.id))
                result.append({
                    'id': pl.id,
                    'name': pl.name,
                    'description': pl.description,
                    'track_count': count
                })
            
            loop.close()
            return jsonify({'playlists': result})
            
        elif request.method == 'POST':
            # Создать новый плейлист
            data = request.json
            name = data.get('name')
            description = data.get('description', '')
            
            if not name:
                return jsonify({'error': 'Name is required'}), 400
                
            playlist = loop.run_until_complete(db.create_playlist(user_id, name, description))
            loop.close()
            
            return jsonify({
                'id': playlist.id,
                'name': playlist.name,
                'description': playlist.description
            })
            
    except Exception as e:
        print(f"❌ Playlists API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/playlists/add_track', methods=['POST'])
def add_track_to_playlist():
    """Добавить трек в плейлист"""
    try:
        user_id = request.headers.get('X-User-ID')
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
            
        data = request.json
        playlist_id = data.get('playlist_id')
        track_data = data.get('track')
        
        if not playlist_id or not track_data:
            return jsonify({'error': 'Missing required data'}), 400
            
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 1. Получаем/создаем трек в БД
        # Генерируем стабильный ID на основе названия и исполнителя
        import hashlib
        track_id = track_data.get('id')
        if not track_id or track_id.startswith('web_'):
            # Создаем уникальный ID на основе исполнителя и названия
            unique_string = f"{track_data.get('artist', '')}_{track_data.get('name', '')}".lower()
            track_id = f"web_{hashlib.md5(unique_string.encode()).hexdigest()[:16]}"
        
        track = loop.run_until_complete(db.get_or_create_track({
            'id': track_id,
            'name': track_data.get('name'),
            'artist': track_data.get('artist'),
            'album': track_data.get('album'),
            'image_url': track_data.get('image'),
            'spotify_url': track_data.get('spotify_url', '')
        }))
        
        # 2. Добавляем в плейлист
        success = loop.run_until_complete(db.add_track_to_playlist(playlist_id, track.id))
        loop.close()
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Track already in playlist'}), 400
            
    except Exception as e:
        print(f"❌ Add track error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/playlists/<int:playlist_id>/tracks', methods=['GET'])
def get_playlist_tracks(playlist_id):
    """Получить треки плейлиста"""
    try:
        user_id = request.headers.get('X-User-ID')
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
            
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Получаем треки плейлиста
        tracks = loop.run_until_complete(db.get_playlist_tracks(playlist_id))
        loop.close()
        
        # Форматируем результат
        result = []
        for track in tracks:
            result.append({
                'id': track.id,
                'name': track.name,
                'artist': track.artist,
                'album': track.album,
                'duration': track.duration_ms // 1000 if track.duration_ms else 0,
                'image': track.image_url,
                'spotify_url': track.spotify_url
            })
        
        return jsonify({'tracks': result})
        
    except Exception as e:
        print(f"❌ Get playlist tracks error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/prepare-stream', methods=['POST'])
def prepare_stream():
    """Подготовить трек для стриминга через Telegram Storage"""
    try:
        data = request.json
        artist = data.get('artist', '')
        track_name = data.get('name', '')
        track_id = data.get('id', '')
        
        if not artist or not track_name:
            return jsonify({'error': 'Artist and track name required'}), 400
        
        # Генерируем уникальный track_id если не передан
        if not track_id:
            import hashlib
            # Используем тот же алгоритм, что и в боте для консистентности
            unique_string = f"{artist}_{track_name}".lower()
            track_id = hashlib.md5(unique_string.encode()).hexdigest()[:16]
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 1. Проверяем кеш в БД (сначала общий кэш бота, затем специфичный для веб-хранилища)
        file_id = loop.run_until_complete(db.get_cached_file_id(track_id, quality='192'))
        
        if not file_id:
            # Проверяем старую таблицу TelegramFile (для совместимости)
            telegram_file = loop.run_until_complete(db.get_telegram_file(track_id))
            if telegram_file:
                file_id = telegram_file.file_id
        
        if file_id:
            # Файл уже в Telegram!
            print(f"✅ Found in cache: {track_id}")
            
            # Получаем прямую ссылку из Telegram
            file_url = get_telegram_storage().get_file_url(file_id)
            
            if file_url:
                loop.close()
                return jsonify({
                    'success': True,
                    'stream_url': file_url,
                    'cached': True,
                    'title': f"{artist} - {track_name}"
                })
        
        # 2. Файла нет в кеше - скачиваем
        print(f"📥 Downloading: {artist} - {track_name}")
        result = loop.run_until_complete(
            download_service.search_and_download(
                artist,
                track_name,
                '192',  # Среднее качество для стриминга
                'mp3'
            )
        )
        
        if not result or result.get('error'):
            error_msg = result.get('error') if result else "Unknown download error"
            print(f"❌ Download failed details: {error_msg}")
            loop.close()
            return jsonify({'error': f"Download failed: {error_msg}"}), 500
            
        if not result.get('file_path') or not os.path.exists(result['file_path']):
            print(f"❌ File not found after download: {result.get('file_path')}")
            loop.close()
            return jsonify({'error': 'File not found after download'}), 500
        
        file_path = result['file_path']
        
        # 3. Загружаем в Telegram Storage
        print(f"📤 Uploading to Telegram Storage: {os.path.basename(file_path)}")
        caption = f"🎵 {artist} - {track_name}"
        upload_result = get_telegram_storage().upload_file(file_path, caption)
        
        if not upload_result or not upload_result.get('file_id'):
            loop.close()
            return jsonify({'error': 'Failed to upload to Telegram Storage'}), 500
        
        # 4. Сохраняем в обе таблицы кэша для максимальной совместимости
        file_id = upload_result['file_id']
        loop.run_until_complete(
            db.update_track_cache(
                track_id=track_id,
                telegram_file_id=file_id,
                file_format='mp3',
                quality='192'
            )
        )
        loop.run_until_complete(
            db.save_telegram_file(
                track_id=track_id,
                file_id=file_id,
                file_path=upload_result.get('file_path'),
                file_size=upload_result.get('file_size'),
                artist=artist,
                track_name=track_name
            )
        )
        
        # 5. Получаем прямую ссылку
        file_url = get_telegram_storage().get_file_url(upload_result['file_id'])
        
        # 6. Очистка временного файла
        try:
            download_service.cleanup_file(file_path)
        except:
            pass
            
        loop.close()
        
        if file_url:
            return jsonify({
                'success': True,
                'stream_url': file_url,
                'cached': False,
                'title': f"{artist} - {track_name}"
            })
        else:
            return jsonify({'error': 'Failed to get stream URL after upload'}), 500
            
    except Exception as e:
        print(f"❌ Prepare stream error: {e}")
        import traceback
        traceback.print_exc()
        # Возвращаем детали ошибки для диагностики
        return jsonify({
            'error': f"Internal Server Error: {str(e)}",
            'type': type(e).__name__
        }), 500

@app.route('/api/stream-file/<path:filename>')
def stream_file(filename):
    """Стримить скачанный файл (legacy, теперь используем Telegram)"""
    try:
        # Получаем абсолютный путь к файлу
        file_path = os.path.join(download_service.download_dir, filename)
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
        
        # Отправляем файл с поддержкой Range requests для HTML5 audio
        return send_file(
            file_path,
            mimetype='audio/mpeg',
            as_attachment=False,
            conditional=True
        )
        
    except Exception as e:
        print(f"❌ Stream file error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/backup-db', methods=['POST'])
def backup_database():
    """Создать backup БД (вызывается при закрытии/обновлении страницы)"""
    try:
        backup_svc = get_backup_service()
        
        # Создаем backup асинхронно
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(backup_svc.backup_to_telegram())
        loop.close()
        
        if success:
            return jsonify({'success': True, 'message': 'Database backup created'})
        else:
            return jsonify({'success': False, 'error': 'Failed to create backup'}), 500
            
    except Exception as e:
        print(f"❌ Backup error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    # Инициализация БД перед запуском
    
    # Запуск сервера
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Web App starting on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)
