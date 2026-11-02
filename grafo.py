"""Grafo de TransferAI: estado compartido, pausas humanas y conexiones entre nodos.

Los agentes están en agentes/. Este archivo no imprime ni lee del teclado: los nodos emiten
eventos (registro.emitir) y las pausas humanas usan interrupt(). Una interfaz (interfaz_terminal.py
o, más adelante, la página HTML) muestra los eventos y responde a las pausas.
Cada pausa entrega un diccionario con la clave "tipo" para que la interfaz sepa qué preguntar.
"""
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agentes.financiero import analizar_finanzas
from agentes.manager import diagnosticar, perfilar_plantilla
from agentes.scouting import hacer_scouting
from config import MAX_RONDAS_SCOUTING, POSICIONES_VALIDAS
from datos import obtener_plantilla, obtener_resumen_club
from registro import emitir


# ---------------------------------------------------------------- ESTADO
class Estado(TypedDict, total=False):
    club: str
    resumen: dict
    plantilla: list
    perfil_posiciones: dict
    diagnostico: dict
    prioridades_confirmadas: list
    lista_corta: list
    lista_final: list
    descartados_ids: list
    feedback_usuario: str
    intentos_scouting: int
    decision_objetivo: str
    jugador_objetivo: dict
    vio_plantilla: bool


# ---------------------------------------------------------------- NODOS DE CÓDIGO
def cargar_club(estado: Estado) -> dict:
    club = estado["club"]
    emitir("info", f"Club cargado: {club}", club=club)
    return {
        "resumen": obtener_resumen_club(club),
        "plantilla": obtener_plantilla(club),
    }


# ---------------------------------------------------------------- PAUSAS HUMANAS
def menu_plantilla(estado: Estado) -> dict:
    """Pausa 1: el usuario decide si quiere ver la plantilla antes del diagnóstico."""
    respuesta = interrupt({
        "tipo": "menu_plantilla",
        "club": estado["club"],
        "n_jugadores": len(estado["plantilla"]),
    })
    opcion = str(respuesta).strip().lower()
    if opcion in ("1", "ver", "plantilla"):
        emitir("plantilla", f"Plantilla de {estado['club']}",
               resumen=estado["resumen"], plantilla=estado["plantilla"])
        return {"vio_plantilla": True}
    if opcion not in ("2", "ir", "recomendaciones"):
        emitir("aviso", "Opción no reconocida; se continúa directamente con las recomendaciones.")
    return {"vio_plantilla": False}


def confirmar_prioridades(estado: Estado) -> dict:
    """Pausa 2: el usuario confirma o cambia las posiciones que propuso el Manager Agent."""
    propuestas = estado["diagnostico"]["posiciones_prioritarias"]
    respuesta = interrupt({"tipo": "confirmar_prioridades", "propuestas": propuestas,
                           "posiciones_validas": POSICIONES_VALIDAS})

    elegidas = []
    for texto in str(respuesta).replace(";", ",").split(","):
        codigo = texto.strip().upper()
        if codigo in POSICIONES_VALIDAS and codigo not in elegidas:
            elegidas.append(codigo)

    if not elegidas:
        elegidas = [p["posicion"] for p in propuestas]
        emitir("aviso", "No se reconoció ninguna posición válida; se mantienen las propuestas del Manager.")

    emitir("info", f"Prioridades confirmadas: {', '.join(elegidas)}", prioridades=elegidas)
    return {"prioridades_confirmadas": elegidas}


def elegir_objetivo(estado: Estado) -> dict:
    """Pausa 3: el usuario elige un candidato, pide otra ronda de scouting o sale."""
    candidatos = estado.get("lista_final", [])
    intentos = estado.get("intentos_scouting", 1)

    respuesta = interrupt({"tipo": "elegir_objetivo", "candidatos": candidatos, "intentos": intentos,
                           "max_rondas": MAX_RONDAS_SCOUTING})
    texto = str(respuesta).strip()
    minuscula = texto.lower()

    if minuscula == "salir":
        emitir("info", "El director deportivo terminó sin elegir un jugador.")
        return {"decision_objetivo": "salir"}

    if minuscula.startswith(("nueva", "nuevo")):
        if intentos >= MAX_RONDAS_SCOUTING:
            emitir("aviso", f"Ya se hicieron {MAX_RONDAS_SCOUTING} rondas de scouting. "
                            "Elige un jugador de la lista o escribe 'salir'.")
            return {"decision_objetivo": "invalido"}
        feedback = texto[5:].lstrip(" :,-").strip()
        ya_vistos = [c["id"] for c in estado.get("lista_corta", [])]
        return {
            "decision_objetivo": "reintentar",
            "feedback_usuario": feedback,
            "descartados_ids": estado.get("descartados_ids", []) + ya_vistos,
        }

    try:
        id_elegido = int(texto)
    except ValueError:
        id_elegido = None
    elegido = next((c for c in candidatos if c["id"] == id_elegido), None)

    if elegido is None:
        emitir("aviso", "Opción no reconocida. Escribe solo el número de id de un candidato, 'nueva' o 'salir'.")
        return {"decision_objetivo": "invalido"}

    emitir("info", f"Jugador objetivo: {elegido['nombre']}", jugador_id=elegido["id"])
    return {"decision_objetivo": "elegido", "jugador_objetivo": elegido}


def decidir_ruta(estado: Estado) -> str:
    decision = estado.get("decision_objetivo")
    if decision in ("elegido", "salir"):
        return "fin"
    if decision == "reintentar":
        return "scouting"
    return "repetir"


# ---------------------------------------------------------------- EL MAPA
def construir_grafo():
    constructor = StateGraph(Estado)
    constructor.add_node("cargar_club", cargar_club)
    constructor.add_node("menu_plantilla", menu_plantilla)
    constructor.add_node("perfilar_plantilla", perfilar_plantilla)
    constructor.add_node("diagnosticar", diagnosticar)
    constructor.add_node("confirmar_prioridades", confirmar_prioridades)
    constructor.add_node("hacer_scouting", hacer_scouting)
    constructor.add_node("analizar_finanzas", analizar_finanzas)
    constructor.add_node("elegir_objetivo", elegir_objetivo)

    constructor.add_edge(START, "cargar_club")
    constructor.add_edge("cargar_club", "menu_plantilla")
    constructor.add_edge("menu_plantilla", "perfilar_plantilla")
    constructor.add_edge("perfilar_plantilla", "diagnosticar")
    constructor.add_edge("diagnosticar", "confirmar_prioridades")
    constructor.add_edge("confirmar_prioridades", "hacer_scouting")
    constructor.add_edge("hacer_scouting", "analizar_finanzas")
    constructor.add_edge("analizar_finanzas", "elegir_objetivo")
    constructor.add_conditional_edges(
        "elegir_objetivo",
        decidir_ruta,
        {"fin": END, "scouting": "hacer_scouting", "repetir": "elegir_objetivo"},
    )
    return constructor.compile(checkpointer=InMemorySaver())


app = construir_grafo()


if __name__ == "__main__":
    # Compatibilidad con el Hito 2: "python grafo.py" sigue funcionando
    from interfaz_terminal import main
    main()
