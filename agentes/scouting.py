"""Scouting & Tactical Agent: busca candidatos con herramientas (ciclo pensar-actuar-observar)."""
import json

from config import MAX_CANDIDATOS_POR_POSICION
from datos import cargar_jugadores, evaluar_encaje
from herramientas import FUNCIONES_SCOUTING, HERRAMIENTAS_SCOUTING
from llm import ejecutar_con_herramientas, extraer_json
from registro import emitir

SISTEMA_SCOUT = """Eres el Scouting & Tactical Agent de un club de fútbol. Recibirás en JSON el club del usuario, su presupuesto de fichajes y las posiciones prioritarias confirmadas por el director deportivo.

Tu tarea es proponer candidatos de OTROS clubes para esas posiciones.

Proceso:
1. Para cada posición prioritaria, usa buscar_jugadores con excluir_club igual al club del usuario y valor_max igual al presupuesto de fichajes. Haz una búsqueda general y otra de promesas (edad_max 21 y ordenar_por "potencial").
2. Si el director pide veteranos, usa edad_min 30. Si pide un rango de calidad, usa rating_min o rating_max. Si pide alto potencial, usa potencial_min.
3. Evalúa a los mejores candidatos con evaluar_encaje, usando el id que entrega la búsqueda.
4. Cada evaluación incluye un tipo_de_fichaje. Propón SOLO candidatos con tipo mejora_inmediata (supera al mejor actual), sucesor_joven (joven que puede relevar a un titular veterano) o promesa (muy joven con potencial superior al mejor actual). Nunca propongas un candidato con tipo no_aporta.
5. Propón como máximo 3 candidatos por posición e intenta incluir tipos distintos cuando existan. En la justificación de un sucesor_joven cita su edad, su rating y la edad_del_mejor_actual; en la de una promesa cita su edad, su rating y su potencial.

Reglas estrictas:
- Usa SOLO datos entregados por las herramientas. No inventes jugadores, ids ni cifras.
- Cada justificación debe citar datos concretos (rating, edad, años de contrato, mejora sobre el mejor actual).
- No juzgues el precio ni el salario: la viabilidad económica la evalúa otro agente.
- Si recibes ids_ya_propuestos, NO propongas a ninguno de esos jugadores: busca otros.
- Si recibes indicacion_del_director, ajusta los filtros de búsqueda a esa indicación (por ejemplo edad_max o valor_max más bajos), sin superar nunca el presupuesto de fichajes.

Responde SOLO con un objeto JSON con esta forma exacta:
{"lista_corta": [{"id": 27, "posicion": "DFC", "justificacion": "..."}]}"""


def validar_candidatos(candidatos, club, prioridades, excluidos=()):
    """El modelo propone ids; los datos oficiales los pone el código."""
    por_id = {j["id"]: j for j in cargar_jugadores()}
    validos, por_posicion = [], {}
    for c in candidatos:
        try:
            jugador = por_id.get(int(c.get("id")))
        except (TypeError, ValueError):
            jugador = None
        if jugador is None:
            emitir("aviso", f"Candidato con id inexistente descartado: {c.get('id')}", agente="scouting")
            continue
        if jugador["id"] in excluidos:
            emitir("aviso", f"Candidato ya propuesto en una ronda anterior: {jugador['nombre']}", agente="scouting")
            continue
        if jugador.get("cedido_por"):
            emitir("aviso", f"Candidato cedido por {jugador['cedido_por']}, no se puede comprar: {jugador['nombre']}",
                   agente="scouting")
            continue
        if jugador["club"] == club or jugador["posicion"] not in prioridades:
            emitir("aviso", f"Candidato no válido descartado: {jugador['nombre']}", agente="scouting")
            continue
        tipo = evaluar_encaje(jugador["id"], club).get("tipo_de_fichaje", "no_aporta")
        if tipo == "no_aporta":
            emitir("aviso", f"Candidato descartado por no aportar al club: {jugador['nombre']}", agente="scouting")
            continue
        if any(v["id"] == jugador["id"] for v in validos):
            continue
        if por_posicion.get(jugador["posicion"], 0) >= MAX_CANDIDATOS_POR_POSICION:
            continue
        por_posicion[jugador["posicion"]] = por_posicion.get(jugador["posicion"], 0) + 1
        validos.append({**jugador, "justificacion": c.get("justificacion", ""), "tipo_de_fichaje": tipo})
    return validos


def hacer_scouting(estado):
    """Nodo del Scouting Agent: el modelo usa herramientas y el código valida cada candidato."""
    club = estado["club"]
    prioridades = estado["prioridades_confirmadas"]
    excluidos = estado.get("descartados_ids", [])

    contexto = {
        "club": club,
        "presupuesto_fichajes": estado["resumen"]["presupuesto_fichajes"],
        "posiciones_prioritarias": prioridades,
        "perfil_posiciones": {p: estado["perfil_posiciones"].get(p) for p in prioridades},
    }
    if excluidos:
        contexto["ids_ya_propuestos"] = excluidos
    if estado.get("feedback_usuario"):
        contexto["indicacion_del_director"] = estado["feedback_usuario"]

    intento = estado.get("intentos_scouting", 0) + 1
    emitir("agente", f"Scouting Agent trabajando (ronda {intento})", agente="scouting", ronda=intento)

    texto = ejecutar_con_herramientas(
        SISTEMA_SCOUT,
        json.dumps(contexto, ensure_ascii=False),
        HERRAMIENTAS_SCOUTING,
        FUNCIONES_SCOUTING,
        agente="scouting",
    )

    lista = []
    if texto is None:
        emitir("aviso", "El Scouting Agent no llegó a una respuesta final.", agente="scouting")
    else:
        try:
            propuestos = extraer_json(texto).get("lista_corta", [])
            lista = validar_candidatos(propuestos, club, prioridades, excluidos)
        except json.JSONDecodeError:
            emitir("error", "La respuesta del Scouting Agent no era un JSON válido.", agente="scouting",
                   respuesta=texto)

    return {"lista_corta": lista, "intentos_scouting": intento}
