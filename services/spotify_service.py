"""
Сервис для работы со Spotify ссылками БЕЗ API
Простой подход: используем oEmbed для названия, YouTube сам найдёт исполнителя
"""
import re
from typing import Optional, Dict
import requests
import httpx
from bs4 import BeautifulSoup


class SpotifyService:
    """Сервис для извлечения информации из Spotify ссылок без API"""
    
    def __init__(self):
        self.session = requests.Session()
        print("✅ Spotify сервис инициализирован (oEmbed)")
    
    @staticmethod
    def parse_spotify_url(url: str) -> Optional[Dict[str, str]]:
        """
        Парсинг Spotify URL
        Возвращает: {'type': 'track'|'album'|'playlist', 'id': 'spotify_id'}
        """
        patterns = {
            'track': r'spotify\.com/track/([a-zA-Z0-9]+)',
            'album': r'spotify\.com/album/([a-zA-Z0-9]+)',
            'playlist': r'spotify\.com/playlist/([a-zA-Z0-9]+)',
        }
        
        for content_type, pattern in patterns.items():
            match = re.search(pattern, url)
            if match:
                return {
                    'type': content_type,
                    'id': match.group(1)
                }
        
        return None
    
    async def get_track_info_from_url(self, url: str) -> Optional[Dict]:
        """
        Получить информацию о треке из Spotify URL
        Использует oEmbed API и Embed страницу для надежности
        """
        try:
            # Очищаем URL от параметров
            clean_url = url.split('?')[0]
            parsed = self.parse_spotify_url(clean_url)
            if not parsed or parsed['type'] != 'track':
                return None
            
            track_id = parsed['id']
            track_name = ""
            artist_name = ""
            image_url = ""
            
            # 1. Сначала пробуем oEmbed для базовой информации
            oembed_url = f"https://open.spotify.com/oembed?url={clean_url}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            }
            
            try:
                response = self.session.get(oembed_url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    track_name = data.get('title', '').strip()
                    image_url = data.get('thumbnail_url')
            except Exception as e:
                print(f"⚠️ oEmbed failed: {e}")
            
            # 2. Если нужно больше данных или oEmbed подвел, используем Embed страницу
            try:
                embed_url = f"https://open.spotify.com/embed/track/{track_id}"
                async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
                    page_response = await client.get(embed_url, timeout=10.0)
                    if page_response.status_code == 200:
                        soup = BeautifulSoup(page_response.text, 'html.parser')
                        script_tag = soup.find('script', {'id': '__NEXT_DATA__', 'type': 'application/json'})
                        
                        if script_tag:
                            import json
                            data = json.loads(script_tag.string)
                            entity = data.get('props', {}).get('pageProps', {}).get('state', {}).get('data', {}).get('entity', {})
                            
                            if entity:
                                if not track_name:
                                    track_name = entity.get('name', '') or entity.get('title', '')
                                
                                # Извлекаем артистов
                                artists = entity.get('artists', [])
                                if artists:
                                    artist_name = ', '.join([a.get('name', '') for a in artists])
                                elif not artist_name:
                                    artist_name = entity.get('subtitle', '').replace('\u00a0', ' ')
                                
                                # Извлекаем картинку если нет
                                if not image_url:
                                    images = entity.get('visualIdentity', {}).get('image', [])
                                    if images:
                                        image_url = images[0].get('url')
            except Exception as e:
                print(f"⚠️ Embed scraping failed: {e}")
            
            if track_name:
                return {
                    'id': track_id,
                    'name': track_name,
                    'artist': artist_name or "Unknown Artist",
                    'image_url': image_url,
                    'spotify_url': clean_url
                }
            
            return None
            
        except Exception as e:
            print(f"❌ Ошибка при получении данных из Spotify: {e}")
            return None
    
    async def get_track_info(self, track_id: str) -> Optional[Dict]:
        """Получить информацию о треке по ID"""
        url = f"https://open.spotify.com/track/{track_id}"
        info = await self.get_track_info_from_url(url)
        if info and not info.get('id'):
            info['id'] = track_id
        return info
    
    async def search_track(self, query: str) -> list:
        """Алиас для веб-приложения"""
        return await self.search_tracks(query)

    async def search_tracks(self, query: str) -> list:
        """
        Поиск треков (недоступен без API)
        Для работы веб-интерфейса возвращаем пустой список, 
        так как поиск по тексту без API в Spotify затруднен.
        """
        print(f"⚠️ Поиск без Spotify API недоступен: {query}")
        return []
    
    def is_playlist_url(self, url: str) -> bool:
        """
        Проверить, является ли URL ссылкой на Spotify плейлист
        
        Args:
            url: URL для проверки
            
        Returns:
            True если это ссылка на плейлист
        """
        parsed = self.parse_spotify_url(url)
        return parsed is not None and parsed['type'] == 'playlist'
    
    async def get_playlist_info(self, playlist_url: str) -> Optional[Dict]:
        """
        Получить информацию о плейлисте через веб-скрапинг
        
        Args:
            playlist_url: URL плейлиста Spotify
            
        Returns:
            Dict с информацией о плейлисте и списком треков
        """
        try:
            
            # Парсим URL для получения ID
            parsed = self.parse_spotify_url(playlist_url)
            if not parsed or parsed['type'] != 'playlist':
                print("❌ Invalid playlist URL")
                return None
            
            playlist_id = parsed['id']
            # Используем EMBED URL для более стабильного скрапинга и обхода защиты
            clean_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            print(f"🔍 Fetching playlist via Embed: {clean_url}")
            
            async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
                response = await client.get(clean_url, timeout=30.0)
                
                if response.status_code != 200:
                    print(f"❌ Failed to fetch playlist embed: HTTP {response.status_code}")
                    return None
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Извлекаем треки из JSON данных в странице (__NEXT_DATA__)
                tracks = []
                playlist_name = "Unknown Playlist"
                
                script_tag = soup.find('script', {'id': '__NEXT_DATA__', 'type': 'application/json'})
                
                if script_tag:
                    import json
                    data = json.loads(script_tag.string)
                    
                    try:
                        # Структура для EMBED страницы: props -> pageProps -> state -> data -> entity
                        entity = data.get('props', {}).get('pageProps', {}).get('state', {}).get('data', {}).get('entity', {})
                        
                        if entity:
                            playlist_name = entity.get('name', playlist_name)
                            items = entity.get('trackList', [])
                            
                            for idx, track_data in enumerate(items):
                                try:
                                    if track_data:
                                        track_name = track_data.get('title', 'Unknown')
                                        # Subtitle в эмбеде содержит артистов
                                        artist_str = track_data.get('subtitle', 'Unknown Artist').replace('\u00a0', ' ')
                                        
                                        # Длительность
                                        duration_ms = track_data.get('duration', 0)
                                        duration_sec = duration_ms // 1000
                                        
                                        # Spotify ID из URI
                                        uri = track_data.get('uri', '')
                                        track_id = uri.split(':')[-1] if uri else f"idx_{idx}"
                                        
                                        tracks.append({
                                            'position': idx + 1,
                                            'id': track_id,
                                            'name': track_name,
                                            'artist': artist_str,
                                            'duration': duration_sec
                                        })
                                        
                                except Exception as e:
                                    print(f"⚠️  Error parsing track {idx}: {e}")
                                    continue
                    
                    except (KeyError, TypeError, AttributeError) as e:
                        print(f"⚠️  Error parsing playlist JSON: {e}")
                
                if not tracks:
                    print("⚠️  Could not extract tracks from playlist embed")
                    return None
                
                print(f"✅ Found {len(tracks)} tracks in playlist '{playlist_name}'")
                
                return {
                    'id': playlist_id,
                    'name': playlist_name,
                    'url': clean_url,
                    'tracks': tracks,
                    'total_tracks': len(tracks)
                }
                
        except Exception as e:
            print(f"❌ Error fetching playlist: {e}")
            import traceback
            traceback.print_exc()
            return None
