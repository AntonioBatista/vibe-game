import os
import json
import random
import asyncio
import aiohttp
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from buscador import BuscadorVibe

app = Flask(__name__)
app.config['SECRET_KEY'] = 'vibe_gold_nexus_2026'

# Configuración optimizada para Render
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', ping_timeout=60, ping_interval=25)
buscador = BuscadorVibe()

COLORES_JUGADORES = ["#00ffcc", "#ff00ff", "#ffff00", "#ff3300", "#0066ff", "#99ff00", "#cc00ff"]

# Estado global
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

@socketio.on('join')
def on_join(data):
    sid = request.sid
    nombre = data.get('nombre', 'Invitado').upper()
    
    # IMPORTANTE: Eliminamos rastreo por IP para que Render no colapse las sesiones
    if sid not in juego["jugadores"]:
        color = COLORES_JUGADORES[len(juego["jugadores"]) % len(COLORES_JUGADORES)]
        juego["jugadores"][sid] = {
            "nombre": nombre, 
            "puntos": 0, 
            "coronas": 0, 
            "color": color
        }
    
    emit('player_config', {"color": juego["jugadores"][sid]["color"]}, room=sid)
    emitir_jugadores()
    socketio.emit('desbloquear_config')

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
        
        claves_seleccionadas = []
        for d in juego["config"]["decadas"]:
            if juego["config"]["solo_espanol"]:
                if f"{d}_es" in biblioteca: claves_seleccionadas.append(f"{d}_es")
            else:
                if f"{d}_es" in biblioteca: claves_seleccionadas.append(f"{d}_es")
                if f"{d}_int" in biblioteca: claves_seleccionadas.append(f"{d}_int")
        
        if not claves_seleccionadas:
            claves_seleccionadas = list(biblioteca.keys())

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def descargar():
            async with aiohttp.ClientSession() as session:
                objetivo = int(juego["config"]["num_canciones"])
                while len(juego["lista_partida"]) < objetivo:
                    clave = random.choice(claves_seleccionadas)
                    item = random.choice(biblioteca[clave])
                    
                    artista = item['artista'] if isinstance(item, dict) else item
                    cancion_fija = item.get('cancion') if isinstance(item, dict) else None
                    
                    datos = await buscador.obtener_datos_cancion(session, artista, cancion_fija, clave.split('_')[0])
                    
                    if datos and datos.get('preview_url'):
                        juego["lista_partida"].append(datos)
                        socketio.emit('progreso_carga', {
                            "count": len(juego["lista_partida"]), 
                            "total": objetivo
                        })
                        socketio.sleep(0.1)

        loop.run_until_complete(descargar())
        enviar_cancion_actual()
    except Exception as e:
        print(f"ERROR EN CARGA: {e}")

def enviar_cancion_actual():
    juego["quien_lo_sabe"] = "BLOQUEADO"
    idx = juego["indice_actual"]
    if idx < len(juego["lista_partida"]):
        datos = juego["lista_partida"][idx]
        socketio.emit('cambio_estado', {"estado": "listo"})
        socketio.sleep(0.5)
        socketio.emit('play_song', {
            "preview": datos['preview_url'], 
            "datos": datos, 
            "quedan": len(juego["lista_partida"]) - idx
        })

@socketio.on('musica_on')
def musica_on():
    juego["quien_lo_sabe"] = None
    socketio.emit('activar_boton_vibe')

@socketio.on('lo_se')
def lo_se_pulsado():
    if juego["quien_lo_sabe"] is None:
        juego["quien_lo_sabe"] = request.sid
        jugador = juego["jugadores"].get(request.sid)
        if jugador:
            socketio.emit('jugador_lo_sabe', {
                "nombre": jugador["nombre"], 
                "color": jugador["color"], 
                "sid": request.sid
            })

@socketio.on('revelar_solucion')
def revelar_solucion():
    idx = juego["indice_actual"]
    if idx < len(juego["lista_partida"]):
        d = juego["lista_partida"][idx]
        socketio.emit('mostrar_info_movil', {
            "artista": d['artista'], 
            "cancion": d['cancion'], 
            "portada": d['portada'], 
            "anyo": d.get('anyo', 'N/A')
        })

@socketio.on('validar_v35')
def manejar_validacion(data):
    sid = data.get('sid')
    if sid in juego["jugadores"]:
        puntos = int(data.get('puntos', 0))
        juego["jugadores"][sid]["puntos"] += puntos
        if data.get('corona'):
            juego["jugadores"][sid]["coronas"] += 1
        
        emitir_jugadores()
        socketio.emit('animar_puntuacion', {
            "puntos_ronda": puntos, 
            "total_puntos": juego["jugadores"][sid]["puntos"], 
            "es_corona": data.get('corona')
        }, room=sid)

@socketio.on('nueva_ronda')
def nueva_ronda():
    juego["indice_actual"] += 1
    if juego["indice_actual"] >= len(juego["lista_partida"]):
        lista = sorted(juego["jugadores"].values(), key=lambda x: (x['puntos'], x['coronas']), reverse=True)
        ganador = lista[0] if lista else {"nombre": "VIBE", "color": "#00ffcc", "puntos": 0}
        socketio.emit('final_partida', {"ganador": ganador})
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
