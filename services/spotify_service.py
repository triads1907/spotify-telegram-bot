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
