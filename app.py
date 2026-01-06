import os
import json
import random
import asyncio
import aiohttp
import socket
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from buscador import BuscadorVibe

app = Flask(__name__)
app.config['SECRET_KEY'] = 'vibe_gold_nexus_2026'

# CLAVE: Permitir que Socket.IO gestione los IDs de sesión de forma independiente
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', ping_timeout=60, ping_interval=25)
buscador = BuscadorVibe()

COLORES_JUGADORES = ["#00ffcc", "#ff00ff", "#ffff00", "#ff3300", "#0066ff", "#99ff00", "#cc00ff"]

juego = {
    "jugadores": {},
    "config": {"modo": "Multijugador", "decadas": [], "solo_espanol": False, "num_canciones": 10},
    "lista_partida": [],
    "indice_actual": 0,
    "server_url": os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'vibe-game-i71y.onrender.com'),
    "quien_lo_sabe": "BLOQUEADO"
}

def emitir_jugadores():
    socketio.emit('update_players', juego["jugadores"])

@app.route('/')
def index():
    return render_template('index.html', ip=juego["server_url"], auto_login=False)

@app.route('/unirse')
def unirse_directo():
    return render_template('index.html', ip=juego["server_url"], auto_login=True)

@app.route('/host')
def host():
    return render_template('host.html', ip=juego["server_url"])

@app.route('/clasico')
def clasico():
    return render_template('clasico.html')

# --- REPARACIÓN DE CONEXIÓN ---
@socketio.on('join')
def on_join(data):
    sid = request.sid # ID único por pestaña de navegador
    nombre = data.get('nombre', 'Invitado').upper()
    
    # IMPORTANTE: No filtramos por IP aquí para evitar el "efecto espejo" en Render
    # Si el SID no existe, es un jugador nuevo garantizado
    if sid not in juego["jugadores"]:
        color = COLORES_JUGADORES[len(juego["jugadores"]) % len(COLORES_JUGADORES)]
        juego["jugadores"][sid] = {
            "nombre": nombre, 
            "puntos": 0, 
            "coronas": 0, 
            "color": color
        }
    
    # Enviamos configuración SOLO al móvil que acaba de entrar
    emit('player_config', {"color": juego["jugadores"][sid]["color"]}, room=sid)
    emitir_jugadores()
    socketio.emit('desbloquear_config')

@socketio.on('lo_se')
def lo_se_pulsado():
    # Solo el primer SID que llega bloquea el pulsador
    if juego["quien_lo_sabe"] is None:
        juego["quien_lo_sabe"] = request.sid
        jugador = juego["jugadores"].get(request.sid)
        if jugador:
            socketio.emit('jugador_lo_sabe', {
                "nombre": jugador["nombre"], 
                "color": jugador["color"], 
                "sid": request.sid
            })

@socketio.on('validar_v35')
def manejar_validacion(data):
    sid = data.get('sid') # Recibimos el SID específico del que pulsó
    if sid in juego["jugadores"]:
        j = juego["jugadores"][sid]
        pts = int(data.get('puntos', 0))
        j["puntos"] += pts
        if data.get('corona'): j["coronas"] += 1
        
        emitir_jugadores()
        # Animamos solo a ese jugador específico
        socketio.emit('animar_puntuacion', {
            "puntos_ronda": pts, 
            "total_puntos": j["puntos"], 
            "es_corona": data.get('corona')
        }, room=sid)

# --- CARGA Y RONDAS (Igual que el anterior pero con SID estable) ---
@socketio.on('pre_configurar')
def pre_configurar(data):
    juego["config"].update(data)
    juego["lista_partida"] = []
    juego["indice_actual"] = 0
    socketio.emit('inicio_carga_masiva', {"total": int(juego["config"]["num_canciones"])})
    socketio.start_background_task(preparar_lote_completo)

def preparar_lote_completo():
    try:
        with open('artistas.json', 'r', encoding='utf-8') as f:
            biblioteca = json.load(f)
        claves = []
        for d in juego["config"]["decadas"]:
            for s in [f"{d}_es", f"{d}_int"]:
                if s in biblioteca:
                    if not (juego["config"]["solo_espanol"] and "_int" in s):
                        claves.append(s)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        async def descargar():
            async with aiohttp.ClientSession() as session:
                while len(juego["lista_partida"]) < int(juego["config"]["num_canciones"]):
                    clave = random.choice(claves)
                    item = random.choice(biblioteca[clave])
                    artista = item['artista'] if isinstance(item, dict) else item
                    fija = item.get('cancion') if isinstance(item, dict) else None
                    datos = await buscador.obtener_datos_cancion(session, artista, fija, clave.split('_')[0])
                    if datos and datos.get('preview_url'):
                        juego["lista_partida"].append(datos)
                        socketio.emit('progreso_carga', {"count": len(juego["lista_partida"]), "total": int(juego["config"]["num_canciones"])})
        loop.run_until_complete(descargar())
        enviar_cancion_actual()
    except Exception as e: print(f"Error: {e}")

def enviar_cancion_actual():
    juego["quien_lo_sabe"] = "BLOQUEADO"
    idx = juego["indice_actual"]
    if idx < len(juego["lista_partida"]):
        datos = juego["lista_partida"][idx]
        socketio.emit('cambio_estado', {"estado": "listo"})
        socketio.sleep(0.5)
        socketio.emit('play_song', {"preview": datos['preview_url'], "datos": datos, "quedan": len(juego["lista_partida"]) - idx})

@socketio.on('musica_on')
def musica_on():
    juego["quien_lo_sabe"] = None
    socketio.emit('activar_boton_vibe')

@socketio.on('revelar_solucion')
def revelar_solucion():
    idx = juego["indice_actual"]
    if idx < len(juego["lista_partida"]):
        d = juego["lista_partida"][idx]
        # IMPORTANTE: Enviamos la información a TODOS para que todos vean la portada
        socketio.emit('mostrar_info_movil', {
            "artista": d['artista'], "cancion": d['cancion'], 
            "portada": d['portada'], "anyo": d.get('anyo', 'N/A')
        })

@socketio.on('nueva_ronda')
def nueva_ronda():
    juego["indice_actual"] += 1
    if juego["indice_actual"] >= len(juego["lista_partida"]):
        lista_final = sorted(juego["jugadores"].values(), key=lambda x: (x['puntos'], x['coronas']), reverse=True)
        socketio.emit('final_partida', {"ganador": lista_final[0] if lista_final else None})
    else:
        socketio.emit('cambio_estado', {"estado": "preparate"})
        socketio.sleep(1.0)
        enviar_cancion_actual()

@socketio.on('reset_total')
def reset_total():
    for sid in juego["jugadores"]:
        juego["jugadores"][sid]["puntos"] = 0
        juego["jugadores"][sid]["coronas"] = 0
    juego["lista_partida"] = []
    juego["indice_actual"] = 0
    emitir_jugadores()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
