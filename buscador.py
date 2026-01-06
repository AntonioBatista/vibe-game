import aiohttp
import asyncio
import urllib.parse
import re
import random

class BuscadorVibe:
    def __init__(self):
        self.base_url = "https://itunes.apple.com/search"

    def limpiar_titulo(self, texto):
        # Patrones para limpiar títulos de canciones y dejar solo el nombre real
        patrones = [
            r'\(.*?Remastered.*?\)', 
            r'\(.*?Live.*?\)', 
            r'\(.*?Edition.*?\)', 
            r'- Remastered.*', 
            r'- Live.*', 
            r'\[.*?\]',
            r'\(feat\..*?\)',
            r'\(with.*?\)',
            r'\(.*?Version.*?\)'
        ]
        resultado = texto
        for p in patrones:
            resultado = re.sub(p, '', resultado, flags=re.IGNORECASE)
        return resultado.strip()

    async def obtener_datos_cancion(self, session, artista, cancion_fija=None, decada=None):
        # Si hay canción fija, buscamos por "Artista Canción", si no, solo por artista
        query = f"{artista} {cancion_fija}" if cancion_fija else artista
        params = {"term": query, "media": "music", "limit": 20, "entity": "song"}
        
        try:
            async with session.get(self.base_url, params=params, timeout=10) as response:
                if response.status != 200: return None
                data = await response.json(content_type=None)
                results = data.get('results', [])
                if not results: return None

                # Lógica de filtrado por década mejorada
                if decada and not cancion_fija:
                    try:
                        # Convertimos "20s" o "80s" en año de inicio
                        # decada[:2] extrae "20", "80", etc.
                        prefix = int(decada[:2])
                        inicio = prefix + (1900 if prefix > 40 else 2000)
                        fin = inicio + 9
                        
                        # Filtramos resultados que caigan en ese rango de 10 años
                        results_filtrados = [r for r in results if inicio <= int(r['releaseDate'][:4]) <= fin]
                        if results_filtrados:
                            results = results_filtrados
                    except:
                        pass # Si falla el parseo, seguimos con los resultados generales

                # Filtro estricto anti-directos y karaoke
                filtrados = [r for r in results if 
                             "live" not in r['trackName'].lower() and 
                             "karaoke" not in r['trackName'].lower() and
                             "tribute" not in r['trackName'].lower()]
                
                track = random.choice(filtrados) if filtrados else results[0]

                titulo_limpio = self.limpiar_titulo(track['trackName'])
                
                # Link de búsqueda en Spotify (más fiable que el anterior)
                search_query = urllib.parse.quote(f"{track['artistName']} {titulo_limpio}")
                spotify_link = f"https://open.spotify.com/search/{search_query}"
                
                return {
                    "artista": track['artistName'],
                    "cancion": titulo_limpio,
                    "anyo": track['releaseDate'][:4],
                    "preview_url": track['previewUrl'],
                    "portada": track['artworkUrl100'].replace("100x100bb", "600x600bb"),
                    "apple_music_url": track['trackViewUrl'],
                    "spotify_url": spotify_link
                }
        except Exception as e:
            print(f"Error crítico en buscador: {e}")
            return None
