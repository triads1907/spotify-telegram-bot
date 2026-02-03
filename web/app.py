"""
Flask Web Application для музыкального бота
"""
from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import sys
import os

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import SpotifyService, DownloadService
from database import DatabaseManager
import asyncio

app = Flask(__name__)
CORS(app)

# Инициализация сервисов
spotify_service = SpotifyService()
download_service = DownloadService()
db = None

async def init_db():
    global db
    db = DatabaseManager()
    await db.init_db()

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
                return jsonify({'error': 'Download failed'}), 500
        
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
            return jsonify({'error': 'Download failed'}), 500
    
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
        track = loop.run_until_complete(db.get_or_create_track({
            'id': track_data.get('id', f"web_{int(asyncio.get_event_loop().time())}"),
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

if __name__ == '__main__':
    # Инициализация БД
    asyncio.run(init_db())
    
    # Запуск сервера
    app.run(host='0.0.0.0', port=5000, debug=True)
