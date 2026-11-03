"""Grafo de TransferAI: estado compartido, pausas humanas y conexiones entre nodos.

Flujo: club -> CENTRO DE MANDO, desde donde el usuario busca refuerzos, revisa la bandeja, avanza días,
ve el estado del club o la plantilla, negocia fichajes o cierra el mercado. El Manager diagnostica la
plantilla al buscar refuerzos por primera vez y otra vez cada vez que la plantilla cambia.
La ventana dura DIAS_VENTANA días (config.py) y se cierra sola al terminar.

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
from config import DIAS_VENTANA, MAX_RONDAS_SCOUTING, POSICIONES_VALIDAS
from datos import obtener_plantilla, obtener_resumen_club, reiniciar_mercado
from registro import emitir
from negociacion import nodos_club as nc
from negociacion import nodos_jugador as nj
from ventana import leer_comando, marcar_leidos, no_leidos


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
    # --- ventana de fichajes (Hito 3)
    dia: int                  # día actual de la ventana (1 a DIAS_VENTANA)
    calendario: list          # eventos futuros (ver ventana.py)
    bandeja: list             # mensajes ya recibidos
    objetivos: list           # jugadores elegidos en el scouting, pendientes de ofertar
    fichajes: list            # operaciones de compra cerradas
    ventas: list              # operaciones de venta cerradas
    comando: str              # última opción elegida en el centro de mando
    dias_a_avanzar: int
    # --- negociaciones (Paso 14)
    negociaciones: dict       # id del jugador -> registro de su negociación (ver negociacion/nodos_club.py)
    negociacion_activa: str   # id del jugador que se está negociando
    texto_usuario: str        # último mensaje escrito por el usuario en una negociación
    interpretacion: dict      # lo que entendió el agente intérprete
    etapa: str                # "primer_contacto" o "ronda"
    resultado_negociacion: str
    tipo_consejo: str         # "manager" o "financiero"
    compromisos: list         # cuotas de traspasos que se pagan en temporadas futuras
    diagnostico_vigente: bool # False cuando la plantilla cambió y el Manager debe volver a analizarla
    candidatos_busqueda: list # todos los candidatos mostrados en las rondas de la búsqueda actual
    siguiente: str            # nodo siguiente que decidió el último nodo de negociación


# ---------------------------------------------------------------- NODOS DE CÓDIGO
def cargar_club(estado: Estado) -> dict:
    club = estado["club"]
    reiniciar_mercado()   # cada partida parte del mercado original
    emitir("info", f"Club cargado: {club}", club=club)
    return {
        "resumen": obtener_resumen_club(club),
        "plantilla": obtener_plantilla(club),
        "dia": 1, "calendario": [], "bandeja": [], "objetivos": [], "fichajes": [], "ventas": [],
        "negociaciones": {}, "compromisos": [], "diagnostico_vigente": False,
    }


# ---------------------------------------------------------------- PAUSAS HUMANAS
def ver_plantilla(estado: Estado) -> dict:
    """Muestra la plantilla actual (incluye los fichajes de la ventana)."""
    emitir("plantilla", f"Plantilla de {estado['club']}",
           resumen=obtener_resumen_club(estado["club"]), plantilla=obtener_plantilla(estado["club"]))
    return {}


ALIAS_POSICIONES = {
    "POR": ["POR"], "PORTERO": ["POR"], "PORTEROS": ["POR"], "ARQUERO": ["POR"], "ARQUEROS": ["POR"], "GK": ["POR"],
    "DFC": ["DFC"], "CENTRAL": ["DFC"], "CENTRALES": ["DFC"],
    "LAT": ["LAT"], "LATERAL": ["LAT"], "LATERALES": ["LAT"],
    "DEF": ["DFC", "LAT"], "DEFENSA": ["DFC", "LAT"], "DEFENSAS": ["DFC", "LAT"],
    "MED": ["MED"], "MEDIO": ["MED"], "MEDIOS": ["MED"], "MEDIOCAMPISTA": ["MED"], "MEDIOCAMPISTAS": ["MED"],
    "VOLANTE": ["MED"], "VOLANTES": ["MED"],
    "EXT": ["EXT"], "EXTREMO": ["EXT"], "EXTREMOS": ["EXT"],
    "DEL": ["DEL"], "DELANTERO": ["DEL"], "DELANTEROS": ["DEL"], "PUNTA": ["DEL"],
}


def leer_posiciones(texto):
    """'DEF, med' -> ['DFC', 'LAT', 'MED']. Acepta códigos y nombres en español."""
    import unicodedata
    limpio = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().upper()
    elegidas = []
    for palabra in limpio.replace(";", ",").replace("/", ",").replace(" Y ", ",").replace(" ", ",").split(","):
        for codigo in ALIAS_POSICIONES.get(palabra.strip(), []):
            if codigo not in elegidas:
                elegidas.append(codigo)
    return elegidas


def confirmar_prioridades(estado: Estado) -> dict:
    """Pausa 2: el usuario confirma o cambia las posiciones que propuso el Manager Agent."""
    propuestas = estado["diagnostico"]["posiciones_prioritarias"]
    respuesta = interrupt({"tipo": "confirmar_prioridades", "propuestas": propuestas,
                           "posiciones_validas": POSICIONES_VALIDAS})

    elegidas = leer_posiciones(respuesta)

    if not elegidas:
        emitir("aviso", f"No se reconoció ninguna posición en '{respuesta}'. Escribe códigos o nombres, "
                        "por ejemplo 'MED', 'DFC, LAT' o 'defensas'.")
        return {"prioridades_confirmadas": []}   # vacío: el grafo vuelve a preguntar

    emitir("info", f"Prioridades confirmadas: {', '.join(elegidas)}", prioridades=elegidas)
    return {"prioridades_confirmadas": elegidas}


def ruta_prioridades(estado: Estado) -> str:
    return "hacer_scouting" if estado.get("prioridades_confirmadas") else "confirmar_prioridades"


def elegir_objetivo(estado: Estado) -> dict:
    """Pausa 3: el usuario elige un candidato, pide otra ronda de scouting o sale."""
    candidatos = estado.get("lista_final", [])
    intentos = estado.get("intentos_scouting", 1)

    respuesta = interrupt({"tipo": "elegir_objetivo", "candidatos": candidatos, "intentos": intentos,
                           "max_rondas": MAX_RONDAS_SCOUTING})
    texto = str(respuesta).strip()
    minuscula = texto.lower()

    if minuscula == "salir":
        emitir("info", "Búsqueda terminada sin elegir un jugador.")
        return {"decision_objetivo": "salir"}

    try:
        id_elegido = int(texto)
    except ValueError:
        id_elegido = None

    # Cualquier texto que no sea un id ni "salir" se toma como indicación para otra ronda
    # ("nueva", "nueva: más jóvenes" o directamente "más jóvenes")
    if id_elegido is None and texto:
        if intentos >= MAX_RONDAS_SCOUTING:
            emitir("aviso", f"Ya se hicieron {MAX_RONDAS_SCOUTING} rondas de scouting. "
                            "Elige un jugador de la lista o escribe 'salir'.")
            return {"decision_objetivo": "invalido"}
        feedback = texto[5:] if minuscula.startswith(("nueva", "nuevo")) else texto
        feedback = feedback.lstrip(" :,-").strip()
        ya_vistos = [c["id"] for c in estado.get("lista_corta", [])]
        return {
            "decision_objetivo": "reintentar",
            "feedback_usuario": feedback,
            "descartados_ids": estado.get("descartados_ids", []) + ya_vistos,
        }

    # Se puede elegir un candidato de cualquier ronda de esta búsqueda
    vistos = {c["id"]: c for c in estado.get("candidatos_busqueda", [])}
    vistos.update({c["id"]: c for c in candidatos})
    elegido = vistos.get(id_elegido)

    if elegido is None:
        emitir("aviso", f"El id {id_elegido} no aparece entre los candidatos de esta búsqueda.")
        return {"decision_objetivo": "invalido"}

    objetivos = estado.get("objetivos", [])
    if any(o["id"] == elegido["id"] for o in objetivos):
        emitir("aviso", f"{elegido['nombre']} ya estaba en tu lista de objetivos.")
    else:
        objetivos = objetivos + [elegido]
        emitir("info", f"{elegido['nombre']} agregado a tu lista de objetivos.", jugador_id=elegido["id"])
    return {"decision_objetivo": "elegido", "jugador_objetivo": elegido, "objetivos": objetivos}


def decidir_ruta(estado: Estado) -> str:
    decision = estado.get("decision_objetivo")
    if decision in ("elegido", "salir"):
        return "centro"
    if decision == "reintentar":
        return "scouting"
    return "repetir"


# ---------------------------------------------------------------- VENTANA DE FICHAJES
def panel(estado: Estado) -> dict:
    """Resumen de la situación que se muestra en el centro de mando."""
    r = estado["resumen"]
    return {
        "club": estado["club"],
        "dia": estado["dia"],
        "dias_restantes": DIAS_VENTANA - estado["dia"],
        "presupuesto_fichajes": r["presupuesto_fichajes"],
        "margen_salarial": r["margen_salarial"],
        "mensajes_nuevos": len(no_leidos(estado.get("bandeja", []))),
        "eventos_pendientes": len(estado.get("calendario", [])),
        "objetivos": [{"id": o["id"], "nombre": o["nombre"], "club": o["club"]} for o in estado.get("objetivos", [])],
        "negociaciones_abiertas": sum(1 for n in estado.get("negociaciones", {}).values() if n["fase"] == "abierta"),
    }


def centro_de_mando(estado: Estado) -> dict:
    """Pausa central de la ventana: el usuario elige la siguiente acción."""
    respuesta = interrupt({"tipo": "centro_de_mando", **panel(estado)})
    comando, dias = leer_comando(respuesta)
    if comando == "invalido":
        emitir("aviso", "Opción no reconocida. Escribe un número del 1 al 7 (por ejemplo '6 5' para avanzar 5 días).")
    return {"comando": comando, "dias_a_avanzar": dias or 1}


def ruta_centro(estado: Estado) -> str:
    return {"buscar": "iniciar_busqueda", "bandeja": "ver_bandeja", "avanzar": "avanzar_dias",
            "estado": "ver_estado", "cerrar": "confirmar_cierre",
            "fichajes": "menu_fichajes", "plantilla": "ver_plantilla"}.get(estado.get("comando"), "centro_de_mando")


def iniciar_busqueda(estado: Estado) -> dict:
    """Reinicia las variables del scouting para una búsqueda nueva."""
    return {"intentos_scouting": 0, "descartados_ids": [], "feedback_usuario": "",
            "lista_corta": [], "lista_final": [], "decision_objetivo": "", "candidatos_busqueda": [],
            "plantilla": obtener_plantilla(estado["club"]), "resumen": obtener_resumen_club(estado["club"])}


def ruta_busqueda(estado: Estado) -> str:
    """El Manager solo vuelve a diagnosticar si la plantilla cambió desde su último análisis."""
    return "confirmar_prioridades" if estado.get("diagnostico_vigente") else "perfilar_plantilla"


def marcar_diagnostico(estado: Estado) -> dict:
    return {"diagnostico_vigente": True}


def ver_bandeja(estado: Estado) -> dict:
    bandeja = estado.get("bandeja", [])
    emitir("bandeja", f"Bandeja de entrada ({len(no_leidos(bandeja))} nuevos)", mensajes=bandeja)
    return {"bandeja": marcar_leidos(bandeja)}


def avanzar_dias(estado: Estado) -> dict:
    """Avanza el tiempo: los eventos del calendario que vencen llegan a la bandeja
    y las respuestas de los clubes actualizan las negociaciones."""
    cambios, cerrada = nc.pasar_dias(estado, estado.get("dias_a_avanzar", 1))
    return {**cambios, "comando": "cierre_automatico" if cerrada else "avanzar"}


def ruta_tras_avanzar(estado: Estado) -> str:
    return "resumen_ventana" if estado.get("comando") == "cierre_automatico" else "centro_de_mando"


def ver_estado(estado: Estado) -> dict:
    emitir("estado_club", f"Estado de {estado['club']} (día {estado['dia']})",
           panel=panel(estado), fichajes=estado.get("fichajes", []), ventas=estado.get("ventas", []),
           calendario=estado.get("calendario", []),
           negociaciones=[{"jugador": n["jugador"]["nombre"], "club": n["club_vendedor"],
                           "estado": nc.ESTADOS_LEGIBLES[n["fase"]]} for n in estado.get("negociaciones", {}).values()])
    return {}


def confirmar_cierre(estado: Estado) -> dict:
    """Cerrar el mercado no se puede deshacer, por eso se pide confirmación."""
    respuesta = interrupt({"tipo": "confirmar_cierre", "dia": estado["dia"],
                           "eventos_pendientes": len(estado.get("calendario", []))})
    confirmado = str(respuesta).strip().lower() in ("s", "si", "sí", "y", "yes")
    if not confirmado:
        emitir("info", "Cierre cancelado; el mercado sigue abierto.")
    return {"comando": "cerrar_confirmado" if confirmado else "cierre_cancelado"}


def ruta_cierre(estado: Estado) -> str:
    return "resumen_ventana" if estado.get("comando") == "cerrar_confirmado" else "centro_de_mando"


def resumen_ventana(estado: Estado) -> dict:
    r = estado["resumen"]
    emitir("resumen_ventana", f"Mercado cerrado el día {estado['dia']}",
           club=estado["club"], dia=estado["dia"], fichajes=estado.get("fichajes", []),
           ventas=estado.get("ventas", []), compromisos=estado.get("compromisos", []),
           presupuesto_final=r["presupuesto_fichajes"],
           margen_salarial_final=r["margen_salarial"], objetivos_sin_cerrar=estado.get("objetivos", []))
    return {}


# ---------------------------------------------------------------- EL MAPA
def construir_grafo():
    g = StateGraph(Estado)
    # Inicio: club, plantilla y diagnóstico (una sola vez)
    g.add_node("cargar_club", cargar_club)
    g.add_node("ver_plantilla", ver_plantilla)
    g.add_node("marcar_diagnostico", marcar_diagnostico)
    g.add_node("perfilar_plantilla", perfilar_plantilla)
    g.add_node("diagnosticar", diagnosticar)
    # Centro de mando y ventana
    g.add_node("centro_de_mando", centro_de_mando)
    g.add_node("ver_bandeja", ver_bandeja)
    g.add_node("avanzar_dias", avanzar_dias)
    g.add_node("ver_estado", ver_estado)
    g.add_node("confirmar_cierre", confirmar_cierre)
    g.add_node("resumen_ventana", resumen_ventana)
    # Búsqueda de refuerzos
    g.add_node("iniciar_busqueda", iniciar_busqueda)
    g.add_node("confirmar_prioridades", confirmar_prioridades)
    g.add_node("hacer_scouting", hacer_scouting)
    g.add_node("analizar_finanzas", analizar_finanzas)
    g.add_node("elegir_objetivo", elegir_objetivo)

    g.add_edge(START, "cargar_club")
    g.add_edge("cargar_club", "centro_de_mando")
    g.add_edge("ver_plantilla", "centro_de_mando")

    g.add_conditional_edges("centro_de_mando", ruta_centro, {
        "iniciar_busqueda": "iniciar_busqueda", "ver_bandeja": "ver_bandeja",
        "avanzar_dias": "avanzar_dias", "ver_estado": "ver_estado",
        "confirmar_cierre": "confirmar_cierre", "centro_de_mando": "centro_de_mando",
        "menu_fichajes": "menu_fichajes", "ver_plantilla": "ver_plantilla"})
    g.add_edge("ver_bandeja", "centro_de_mando")
    g.add_edge("ver_estado", "centro_de_mando")
    g.add_conditional_edges("avanzar_dias", ruta_tras_avanzar,
                            {"resumen_ventana": "resumen_ventana", "centro_de_mando": "centro_de_mando"})
    g.add_conditional_edges("confirmar_cierre", ruta_cierre,
                            {"resumen_ventana": "resumen_ventana", "centro_de_mando": "centro_de_mando"})
    g.add_edge("resumen_ventana", END)

    g.add_conditional_edges("iniciar_busqueda", ruta_busqueda,
                            {"confirmar_prioridades": "confirmar_prioridades", "perfilar_plantilla": "perfilar_plantilla"})
    g.add_edge("perfilar_plantilla", "diagnosticar")
    g.add_edge("diagnosticar", "marcar_diagnostico")
    g.add_edge("marcar_diagnostico", "confirmar_prioridades")
    g.add_conditional_edges("confirmar_prioridades", ruta_prioridades,
                            {"hacer_scouting": "hacer_scouting", "confirmar_prioridades": "confirmar_prioridades"})
    g.add_edge("hacer_scouting", "analizar_finanzas")
    g.add_edge("analizar_finanzas", "elegir_objetivo")
    g.add_conditional_edges("elegir_objetivo", decidir_ruta, {
        "centro": "centro_de_mando", "scouting": "hacer_scouting", "repetir": "elegir_objetivo"})

    # Negociación con el club vendedor (Paso 14): cada nodo decide el siguiente en estado["siguiente"]
    nodos_negociacion = {
        "menu_fichajes": nc.menu_fichajes,
        "escribir_primer_contacto": nc.escribir_primer_contacto,
        "interpretar_primer_contacto": nc.interpretar_primer_contacto,
        "confirmar_interpretacion": nc.confirmar_interpretacion,
        "enviar_primer_contacto": nc.enviar_primer_contacto,
        "entrar_negociacion": nc.entrar_negociacion,
        "turno_comprador": nc.turno_comprador,
        "interpretar_turno": nc.interpretar_turno,
        "dar_consejo": nc.dar_consejo,
        "responder_vendedor": nc.responder_vendedor,
        "cerrar_negociacion_club": nc.cerrar_negociacion_club,
        # Negociación con el jugador y cierre del fichaje (Paso 15)
        "entrar_negociacion_jugador": nj.entrar_negociacion_jugador,
        "turno_jugador": nj.turno_jugador,
        "interpretar_turno_jugador": nj.interpretar_turno_jugador,
        "dar_consejo_jugador": nj.dar_consejo_jugador,
        "responder_agente_jugador": nj.responder_agente_jugador,
        "cerrar_fichaje": nj.cerrar_fichaje,
    }
    for nombre, funcion in nodos_negociacion.items():
        g.add_node(nombre, funcion)
    destinos = {n: n for n in nodos_negociacion} | {"centro_de_mando": "centro_de_mando",
                                                     "resumen_ventana": "resumen_ventana"}
    seguir = lambda estado: estado["siguiente"]
    for nombre in ("menu_fichajes", "escribir_primer_contacto", "interpretar_primer_contacto",
                   "confirmar_interpretacion", "enviar_primer_contacto", "interpretar_turno",
                   "dar_consejo", "responder_vendedor", "cerrar_negociacion_club",
                   "interpretar_turno_jugador", "dar_consejo_jugador", "responder_agente_jugador", "cerrar_fichaje"):
        g.add_conditional_edges(nombre, seguir, destinos)
    g.add_edge("entrar_negociacion", "turno_comprador")
    g.add_edge("turno_comprador", "interpretar_turno")
    g.add_edge("entrar_negociacion_jugador", "turno_jugador")
    g.add_edge("turno_jugador", "interpretar_turno_jugador")
    return g.compile(checkpointer=InMemorySaver())


app = construir_grafo()


if __name__ == "__main__":
    # Compatibilidad con el Hito 2: "python grafo.py" sigue funcionando
    from interfaz_terminal import main
    main()
