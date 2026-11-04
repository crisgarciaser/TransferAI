"""Interfaz web de TransferAI (alternativa a interfaz_terminal.py).

Se ejecuta con:  python web.py   y se abre en el navegador:  http://localhost:5000

Cómo funciona: el grafo (grafo.py) es el mismo que usa la terminal. Este servidor lo ejecuta en
segundo plano y la página (carpeta web/) le consulta cada medio segundo qué pasó:
- "pausa": la pausa humana actual del grafo (su "tipo" decide qué pantalla se dibuja),
- "eventos": lo que emitieron los agentes desde la última consulta (registro.emitir),
- "juego": una foto del estado de la partida (presupuesto, plantilla, bandeja...).
Cuando el usuario responde, la respuesta se entrega al grafo con Command(resume=...).
"""
import threading

from flask import Flask, jsonify, request, send_from_directory
from langgraph.types import Command

from config import DIAS_PLAZO_JUGADOR
from datos import cargar_clubes, obtener_plantilla, obtener_resumen_club, reiniciar_mercado
from grafo import app as grafo
from registro import emitir, iniciar_sesion, suscribir
from tactica import identidad_tactica, perfil_tactico

servidor = Flask(__name__, static_folder="web", static_url_path="")

# Una sola partida a la vez (la demo es para un usuario)
sesion = {"config": None, "eventos": [], "pausa": None, "ocupado": False, "fin": False, "error": None}
candado = threading.Lock()


def _guardar_evento(evento):
    if evento["tipo"] != "llm":          # las llamadas al modelo solo quedan en el log
        sesion["eventos"].append(evento)


suscribir(_guardar_evento)


def _ejecutar(entrada):
    """Corre el grafo hasta la siguiente pausa (en un hilo aparte, para no congelar la página)."""
    try:
        resultado = grafo.invoke(entrada, sesion["config"])
        if "__interrupt__" in resultado:
            sesion["pausa"] = resultado["__interrupt__"][0].value
        else:
            sesion["pausa"], sesion["fin"] = None, True
    except Exception as e:          # el error se muestra en la página en vez de botar el servidor
        sesion["error"] = f"{type(e).__name__}: {e}"
        emitir("error", f"Error interno: {e}")
    finally:
        sesion["ocupado"] = False


def _lanzar(entrada):
    sesion["ocupado"], sesion["error"] = True, None
    threading.Thread(target=_ejecutar, args=(entrada,), daemon=True).start()


def _foto_del_juego():
    """Datos de la partida que la página necesita para dibujar las pantallas."""
    if not sesion["config"]:
        return None
    valores = grafo.get_state(sesion["config"]).values
    club = valores.get("club")
    if not club:
        return None
    ficha_club = next((c for c in cargar_clubes() if c["club"] == club), None)
    plantilla = [{**j, "perfil_tactico": perfil_tactico(j)} for j in obtener_plantilla(club)]
    return {
        "club": club,
        "dia": valores.get("dia", 1),
        "resumen": obtener_resumen_club(club),
        "identidad": identidad_tactica(ficha_club) if ficha_club else None,
        "plantilla": plantilla,
        "diagnostico": valores.get("diagnostico"),
        "diagnostico_vigente": valores.get("diagnostico_vigente", False),
        "calendario": valores.get("calendario", []),
        "bandeja": valores.get("bandeja", []),
        "objetivos": [{"id": o["id"], "nombre": o["nombre"], "club": o["club"]} for o in valores.get("objetivos", [])],
        "fichajes": valores.get("fichajes", []),
        "ventas": valores.get("ventas", []),
        "plazos_jugador": [
            {"jugador": n["jugador"]["nombre"], "dia": n.get("dia_acuerdo", 0) + DIAS_PLAZO_JUGADOR}
            for n in valores.get("negociaciones", {}).values() if n.get("fase") == "acuerdo_club"],
    }


@servidor.get("/")
def inicio():
    return send_from_directory("web", "index.html")


@servidor.get("/api/clubes")
def clubes():
    return jsonify(sorted(c["club"] for c in cargar_clubes()))


@servidor.post("/api/nueva")
def nueva_partida():
    club = (request.get_json(silent=True) or {}).get("club", "")
    if club not in {c["club"] for c in cargar_clubes()}:
        return jsonify({"error": "Club no encontrado"}), 400
    with candado:
        if sesion["ocupado"]:
            return jsonify({"error": "Espera a que termine la acción en curso"}), 409
        reiniciar_mercado()
        archivo = iniciar_sesion()
        sesion.update(config={"configurable": {"thread_id": archivo.stem}, "recursion_limit": 200},
                      eventos=[], pausa=None, fin=False)
        _lanzar({"club": club})
    return jsonify({"ok": True, "log": archivo.name})


@servidor.post("/api/responder")
def responder():
    respuesta = str((request.get_json(silent=True) or {}).get("respuesta", ""))
    with candado:
        if sesion["ocupado"] or sesion["pausa"] is None:
            return jsonify({"error": "No hay una pausa esperando respuesta"}), 409
        emitir("respuesta_usuario", respuesta, pausa=sesion["pausa"]["tipo"])
        sesion["pausa"] = None
        _lanzar(Command(resume=respuesta))
    return jsonify({"ok": True})


@servidor.get("/api/estado")
def estado():
    desde = request.args.get("desde", 0, type=int)
    return jsonify({
        "ocupado": sesion["ocupado"], "fin": sesion["fin"], "error": sesion["error"],
        "pausa": sesion["pausa"], "eventos": sesion["eventos"][desde:], "total": len(sesion["eventos"]),
        "juego": None if sesion["ocupado"] else _foto_del_juego(),
    })


if __name__ == "__main__":
    print("TransferAI web: abre http://localhost:5000 en tu navegador (Ctrl+C para cerrar)")
    servidor.run(port=5000, debug=False, threaded=True)
