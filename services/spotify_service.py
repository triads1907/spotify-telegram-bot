"""
Сервис для работы со Spotify ссылками БЕЗ API
Простой подход: используем oEmbed для названия, YouTube сам найдёт исполнителя
"""
import re
from typing import Optional, Dict
import requests


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
    
    def get_track_info_from_url(self, url: str) -> Optional[Dict]:
        """
        Получить информацию о треке из Spotify URL
        Использует oEmbed API для получения названия и обложки
        """
        try:
            # Очищаем URL от параметров
            clean_url = url.split('?')[0]
            
            # Сначала пробуем oEmbed для базовой информации
            oembed_url = f"https://open.spotify.com/oembed?url={clean_url}"
            track_name = ""
            image_url = ""
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            try:
                response = self.session.get(oembed_url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    track_name = data.get('title', '').strip()
                    image_url = data.get('thumbnail_url')
            except Exception as e:
                print(f"⚠️ oEmbed failed, falling back to scraping: {e}")
            
            # Теперь получаем HTML страницы для извлечения Артиста
            artist_name = ""
            try:
                page_response = self.session.get(clean_url, headers=headers, timeout=5)
                if page_response.status_code == 200:
                    html = page_response.text
                    
                    # Способ 1: Из тега <title>
                    # "Track Name - song and lyrics by Artist | Spotify"
                    title_match = re.search(r'<title>([^<]+)</title>', html)
                    if title_match:
                        title_text = title_match.group(1)
                        if " - song " in title_text and " by " in title_text:
                            artist_part = title_text.split(" by ")[1].split(" | Spotify")[0]
                            artist_name = artist_part.strip()
                            if not track_name:
                                track_name = title_text.split(" - song ")[0].strip()
                    
                    # Способ 2: Из og:description (если 1 не сработал)
                    if not artist_name:
                        desc_match = re.search(r'<meta property="og:description" content="([^"]+)"', html)
                        if desc_match:
                            content = desc_match.group(1)
                            # "Artist · Song · Year"
                            parts = content.split(" · ")
                            if len(parts) >= 2:
                                artist_name = parts[0].strip()
                                if not track_name:
                                    track_name = parts[1].strip()
            except Exception as e:
                print(f"⚠️ Scraping failed: {e}")
            
            if track_name:
                # Извлекаем ID из URL для консистентности
                parsed = self.parse_spotify_url(clean_url)
                track_id = parsed['id'] if parsed else None
                
                return {
                    'id': track_id,
                    'name': track_name,
                    'artist': artist_name,
                    'image_url': image_url,
                    'spotify_url': clean_url
                }
            
            return None
            
        except Exception as e:
            print(f"❌ Ошибка при получении данных из Spotify: {e}")
            return None
    
    def get_track_info(self, track_id: str) -> Optional[Dict]:
        """Получить информацию о треке по ID"""
        url = f"https://open.spotify.com/track/{track_id}"
        info = self.get_track_info_from_url(url)
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
            from bs4 import BeautifulSoup
            import httpx
            
            # Парсим URL для получения ID
            parsed = self.parse_spotify_url(playlist_url)
            if not parsed or parsed['type'] != 'playlist':
                print("❌ Invalid playlist URL")
                return None
            
            playlist_id = parsed['id']
            clean_url = f"https://open.spotify.com/playlist/{playlist_id}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            print(f"🔍 Fetching playlist: {clean_url}")
            
            async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
                response = await client.get(clean_url, timeout=30.0)
                
                if response.status_code != 200:
                    print(f"❌ Failed to fetch playlist: HTTP {response.status_code}")
                    return None
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Извлекаем название плейлиста из meta tags
                playlist_name = "Unknown Playlist"
                og_title = soup.find('meta', property='og:title')
                if og_title:
                    playlist_name = og_title.get('content', playlist_name)
                
                # Извлекаем треки из JSON данных в странице
                tracks = []
                script_tag = soup.find('script', {'id': '__NEXT_DATA__', 'type': 'application/json'})
                
                if script_tag:
                    import json
                    data = json.loads(script_tag.string)
                    
                    try:
                        # Навигация по структуре JSON
                        playlist_data = data.get('props', {}).get('pageProps', {}).get('state', {}).get('data', {}).get('playlistV2', {})
                        
                        if 'content' in playlist_data:
                            items = playlist_data['content'].get('items', [])
                            
                            for idx, item in enumerate(items):
                                try:
                                    track_data = item.get('itemV2', {}).get('data', {})
                                    
                                    if track_data:
                                        track_name = track_data.get('name', 'Unknown')
                                        
                                        # Извлекаем исполнителей
                                        artists = track_data.get('artists', {}).get('items', [])
                                        artist_names = [artist.get('profile', {}).get('name', '') for artist in artists]
                                        artist_str = ', '.join(filter(None, artist_names)) or 'Unknown Artist'
                                        
                                        # Длительность
                                        duration_ms = track_data.get('trackDuration', {}).get('totalMilliseconds', 0)
                                        duration_sec = duration_ms // 1000
                                        
                                        tracks.append({
                                            'position': idx + 1,
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
                    print("⚠️  Could not extract tracks from playlist")
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
