import aiohttp
import asyncio
import urllib.parse
import re
import random

class BuscadorVibe:
    def __init__(self):
        self.base_url = "https://itunes.apple.com/search"

    def limpiar_titulo(self, texto):
        patrones = [
            r'\(.*?Remastered.*?\)', 
            r'\(.*?Live.*?\)', 
            r'\(.*?Edition.*?\)', 
            r'- Remastered.*', 
            r'- Live.*', 
            r'\[.*?\]',
            r'\(feat\..*?\)',
            r'\(with.*?\)'
        ]
        resultado = texto
        for p in patrones:
            resultado = re.sub(p, '', resultado, flags=re.IGNORECASE)
        return resultado.strip()

    async def obtener_datos_cancion(self, session, artista, cancion_fija=None, decada=None):
        query = f"{artista} {cancion_fija}" if cancion_fija else artista
        params = {"term": query, "media": "music", "limit": 15, "entity": "song"}
        
        try:
            async with session.get(self.base_url, params=params) as response:
                if response.status != 200: return None
                data = await response.json(content_type=None)
                results = data.get('results', [])
                if not results: return None

                # Filtro de década (solo si no es canción fija)
                if decada and not cancion_fija:
                    try:
                        anyo_base = int(decada[:2])
                        inicio = anyo_base + (1900 if anyo_base > 40 else 2000)
                        results = [r for r in results if inicio <= int(r['releaseDate'][:4]) <= inicio + 9]
                    except: pass

                if not results: results = data.get('results', [])
                
                # Filtro anti-directos
                filtrados = [r for r in results if "live" not in r['trackName'].lower() and "karaoke" not in r['trackName'].lower()]
                track = random.choice(filtrados) if filtrados else results[0]

                titulo_limpio = self.limpiar_titulo(track['trackName'])
                search_query = urllib.parse.quote(f"{track['artistName']} {titulo_limpio}")
                
                return {
                    "artista": track['artistName'],
                    "cancion": titulo_limpio,
                    "anyo": track['releaseDate'][:4],
                    "preview_url": track['previewUrl'],
                    "portada": track['artworkUrl100'].replace("100x100bb", "600x600bb"),
                    "apple_music_url": track['trackViewUrl'],
                    "spotify_url": f"https://open.spotify.com/search/{search_query}"
                }
        except Exception as e:
            print(f"Error buscador: {e}")
            return None