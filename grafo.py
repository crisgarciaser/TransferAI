import json
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
import unicodedata

from datos import (
    analizar_viabilidad,
    cargar_clubes,
    cargar_jugadores,
    obtener_plantilla,
    obtener_resumen_club,
)
from herramientas import FUNCIONES_SCOUTING, HERRAMIENTAS_SCOUTING
from llm import consultar_json, ejecutar_con_herramientas, extraer_json

MAX_INTENTOS_SCOUTING = 3
POSICIONES_VALIDAS = {"POR", "DFC", "LAT", "MED", "EXT", "DEL"}


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


# ---------------------------------------------- PASOS 1-2: CARGA Y PERFIL
def cargar_club(estado: Estado) -> dict:
    club = estado["club"]
    return {
        "resumen": obtener_resumen_club(club),
        "plantilla": obtener_plantilla(club),
    }


def perfilar_plantilla(estado: Estado) -> dict:
    por_posicion = {}
    for j in estado["plantilla"]:
        por_posicion.setdefault(j["posicion"], []).append(j)

    perfil = {}
    for pos, jugadores in por_posicion.items():
        perfil[pos] = {
            "jugadores": len(jugadores),
            "edad_media": round(sum(j["edad"] for j in jugadores) / len(jugadores), 1),
            "mejor_rating": max(j["rating"] for j in jugadores),
            "contratos_por_vencer": sum(1 for j in jugadores if j["anios_contrato"] <= 1),
        }
    return {"perfil_posiciones": perfil}


# ------------------------------------------------------ MANAGER AGENT
SISTEMA_MANAGER = """Eres el Manager Agent de un club de fútbol y asesoras al director deportivo.
Recibirás en JSON el resumen financiero del club, el perfil de su plantilla por posición y la lista de jugadores.
Entrega un diagnóstico de la plantilla.

Reglas estrictas:
- Usa SOLO los datos entregados. No inventes cifras, jugadores ni reglas (por ejemplo, cupos de extranjeros) ni menciones datos que no se te dieron (pie hábil, lesiones, etc.).
- Las posiciones se escriben con los códigos POR, DFC, LAT, MED, EXT, DEL.
- Máximo 3 posiciones prioritarias, ordenadas de más a menos urgente.
- Cada motivo debe apoyarse en datos concretos (edad, rating, años de contrato, cantidad de jugadores).
- Copia los nombres de los jugadores EXACTAMENTE como aparecen en la lista entregada.
- Considera prescindible solo a un jugador que no aporta y cuya salida no deje la plantilla corta. Si la plantilla tiene menos de 18 jugadores, sé muy conservador y deja la lista vacía si no hay un caso claro.

Responde SOLO con un objeto JSON con esta forma exacta:
{
  "fortalezas": ["..."],
  "debilidades": ["..."],
  "posiciones_prioritarias": [{"posicion": "DFC", "urgencia": "alta|media|baja", "motivo": "..."}],
  "jugadores_prescindibles": [{"nombre": "...", "motivo": "..."}],
  "restricciones": "texto breve sobre presupuesto de fichajes y margen salarial"
}"""


def validar_nombres(diagnostico, plantilla):
    """Elimina jugadores que el modelo mencionó pero que no existen en la plantilla."""
    nombres = {j["nombre"] for j in plantilla}
    validos = []
    for item in diagnostico.get("jugadores_prescindibles", []):
        if item.get("nombre") in nombres:
            validos.append(item)
        else:
            print(f"AVISO: el modelo mencionó un jugador inexistente: {item.get('nombre')}")
    diagnostico["jugadores_prescindibles"] = validos
    return diagnostico


def diagnosticar(estado: Estado) -> dict:
    plantilla_simple = [
        {
            "nombre": j["nombre"],
            "posicion": j["posicion"],
            "edad": j["edad"],
            "rating": j["rating"],
            "anios_contrato": j["anios_contrato"],
            "salario_anual": j["salario_anual"],
            "titular": j["titular"],
        }
        for j in estado["plantilla"]
    ]
    datos = {
        "resumen_club": estado["resumen"],
        "perfil_posiciones": estado["perfil_posiciones"],
        "plantilla": plantilla_simple,
    }
    diagnostico = consultar_json(SISTEMA_MANAGER, json.dumps(datos, ensure_ascii=False))
    diagnostico = validar_nombres(diagnostico, estado["plantilla"])
    return {"diagnostico": diagnostico}


# ------------------------------------------------ PASO 3: PAUSA HUMANA 1
def confirmar_prioridades(estado: Estado) -> dict:
    propuestas = estado["diagnostico"]["posiciones_prioritarias"]

    # El grafo se detiene aquí y espera la decisión del usuario
    respuesta = interrupt({"propuestas": propuestas})

    elegidas = []
    for texto in str(respuesta).replace(";", ",").split(","):
        codigo = texto.strip().upper()
        if codigo in POSICIONES_VALIDAS and codigo not in elegidas:
            elegidas.append(codigo)

    if not elegidas:
        elegidas = [p["posicion"] for p in propuestas]
        print("No se reconoció ninguna posición válida; se mantienen las propuestas del Manager.")

    return {"prioridades_confirmadas": elegidas}


# ---------------------------------------------------- SCOUTING AGENT
SISTEMA_SCOUT = """Eres el Scouting & Tactical Agent de un club de fútbol. Recibirás en JSON el club del usuario, su presupuesto de fichajes y las posiciones prioritarias confirmadas por el director deportivo.

Tu tarea es proponer candidatos de OTROS clubes para esas posiciones.

Proceso:
1. Para cada posición prioritaria, usa buscar_jugadores con excluir_club igual al club del usuario y valor_max igual al presupuesto de fichajes.
2. Evalúa a los mejores candidatos con evaluar_encaje, usando el id que entrega la búsqueda.
3. Propón como máximo 3 candidatos por posición. Si ningún jugador mejora al mejor actual de esa posición (mejora_sobre_el_mejor_actual menor o igual a 0), no propongas a nadie para ella.

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
            print(f"AVISO: candidato con id inexistente descartado: {c.get('id')}")
            continue
        if jugador["id"] in excluidos:
            print(f"AVISO: candidato ya propuesto en una ronda anterior: {jugador['nombre']}")
            continue
        if jugador["club"] == club or jugador["posicion"] not in prioridades:
            print(f"AVISO: candidato no válido descartado: {jugador['nombre']}")
            continue
        if any(v["id"] == jugador["id"] for v in validos):
            continue
        if por_posicion.get(jugador["posicion"], 0) >= 3:
            continue
        por_posicion[jugador["posicion"]] = por_posicion.get(jugador["posicion"], 0) + 1
        validos.append({**jugador, "justificacion": c.get("justificacion", "")})
    return validos


def hacer_scouting(estado: Estado) -> dict:
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
    print(f"\n--- Scouting Agent trabajando (ronda {intento}) ---")

    texto = ejecutar_con_herramientas(
        SISTEMA_SCOUT,
        json.dumps(contexto, ensure_ascii=False),
        HERRAMIENTAS_SCOUTING,
        FUNCIONES_SCOUTING,
    )

    lista = []
    if texto is None:
        print("AVISO: el Scouting Agent no llegó a una respuesta final.")
    else:
        try:
            propuestos = extraer_json(texto).get("lista_corta", [])
            lista = validar_candidatos(propuestos, club, prioridades, excluidos)
        except json.JSONDecodeError:
            print("AVISO: respuesta del Scouting Agent no era un JSON válido:\n", texto)

    return {"lista_corta": lista, "intentos_scouting": intento}


# ------------------------------------------------------ FINANCIAL AGENT
SISTEMA_FINANCIERO = """Eres el Financial Agent de un club de fútbol: el auditor que revisa la viabilidad económica de cada fichaje candidato.
Recibirás en JSON una lista de candidatos con sus cifras ya calculadas por el sistema.

Reglas estrictas:
- Usa SOLO las cifras entregadas. No recalcules ni inventes montos.
- No cambies el veredicto entregado.
- Para cada candidato escribe un comentario de una sola frase (máximo 25 palabras) que cite al menos una cifra concreta.
- Copia el id de cada candidato tal como se entregó.

Responde SOLO con un objeto JSON con esta forma exacta:
{"comentarios": [{"id": 27, "comentario": "..."}]}"""


def analizar_finanzas(estado: Estado) -> dict:
    analizados = []
    for c in estado["lista_corta"]:
        analisis = analizar_viabilidad(c, estado["resumen"])
        analizados.append({**c, "analisis": analisis, "comentario": ""})

    viables = []
    for c in analizados:
        if c["analisis"]["veredicto"] == "inviable":
            motivo = "; ".join(c["analisis"]["alertas"])
            print(f"Descartado por el Financial Agent: {c['nombre']} ({motivo})")
        else:
            viables.append(c)

    if viables:
        datos = [{"id": c["id"], "nombre": c["nombre"], **c["analisis"]} for c in viables]
        try:
            respuesta = consultar_json(SISTEMA_FINANCIERO, json.dumps(datos, ensure_ascii=False))
            comentarios = {int(x["id"]): x["comentario"] for x in respuesta.get("comentarios", [])}
            for c in viables:
                c["comentario"] = comentarios.get(c["id"], "")
        except Exception:
            print("AVISO: no se pudieron generar los comentarios del Financial Agent.")

    return {"lista_final": viables}


# ------------------------------------------------ PASO 4: PAUSA HUMANA 2
def elegir_objetivo(estado: Estado) -> dict:
    candidatos = estado.get("lista_final", [])
    intentos = estado.get("intentos_scouting", 1)

    respuesta = interrupt({"candidatos": candidatos, "intentos": intentos})

    texto = str(respuesta).strip()
    minuscula = texto.lower()

    if minuscula == "salir":
        print("Has decidido terminar sin elegir un jugador.")
        return {"decision_objetivo": "salir"}

    if minuscula.startswith("nueva"):
        if intentos >= MAX_INTENTOS_SCOUTING:
            print(f"Ya se hicieron {MAX_INTENTOS_SCOUTING} rondas de scouting. "
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
        print("Opción no reconocida. Escribe solo el número de id de un candidato, 'nueva' o 'salir'.")
        return {"decision_objetivo": "invalido"}

    return {"decision_objetivo": "elegido", "jugador_objetivo": elegido}


def decidir_ruta(estado: Estado) -> str:
    decision = estado.get("decision_objetivo")
    if decision in ("elegido", "salir"):
        return "fin"
    if decision == "reintentar":
        return "scouting"
    return "repetir"


# ------------------------------------------------------------- EL MAPA
constructor = StateGraph(Estado)
constructor.add_node("cargar_club", cargar_club)
constructor.add_node("perfilar_plantilla", perfilar_plantilla)
constructor.add_node("diagnosticar", diagnosticar)
constructor.add_node("confirmar_prioridades", confirmar_prioridades)
constructor.add_node("hacer_scouting", hacer_scouting)
constructor.add_node("analizar_finanzas", analizar_finanzas)
constructor.add_node("elegir_objetivo", elegir_objetivo)

constructor.add_edge(START, "cargar_club")
constructor.add_edge("cargar_club", "perfilar_plantilla")
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

app = constructor.compile(checkpointer=InMemorySaver())

def _normalizar(texto):
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower().strip()


def elegir_club():
    clubes = [c["club"] for c in cargar_clubes()]
    while True:
        texto = _normalizar(input("\nEscribe el club que quieres gestionar (o parte del nombre): "))
        if not texto:
            continue
        exactas = [c for c in clubes if _normalizar(c) == texto]
        if exactas:
            return exactas[0]
        coincidencias = [c for c in clubes if texto in _normalizar(c)]
        if len(coincidencias) == 1:
            return coincidencias[0]
        if not coincidencias:
            print("No encontré ningún club con ese nombre. Intenta de nuevo.")
        else:
            print("Hay varias coincidencias:", ", ".join(coincidencias[:10]))

# ----------------------------------------------------------- EJECUCIÓN
if __name__ == "__main__":
    config = {"configurable": {"thread_id": "sesion-1"}}
    club = elegir_club()
    resultado = app.invoke({"club": club}, config)

    while "__interrupt__" in resultado:
        pausa = resultado["__interrupt__"][0].value

        if "propuestas" in pausa:
            print("\n=== PROPUESTA DEL MANAGER AGENT ===")
            for p in pausa["propuestas"]:
                print(f"- {p['posicion']} (urgencia {p['urgencia']}): {p['motivo']}")
            print("\nPosiciones válidas: POR, DFC, LAT, MED, EXT, DEL")
            decision = input("¿Qué posiciones quieres priorizar? (separa con comas, ej: DFC,MED): ")
        else:
            print(f"\n=== CANDIDATOS EVALUADOS (ronda {pausa['intentos']}) ===")
            if not pausa["candidatos"]:
                print("No hay candidatos viables en esta ronda.")
            for c in pausa["candidatos"]:
                a = c["analisis"]
                print(f"[id {c['id']}] {c['nombre']} ({c['posicion']}, {c['edad']} años, {c['club']}) "
                      f"rating {c['rating']} - {a['veredicto'].upper()}")
                print(f"   Traspaso estimado {a['traspaso_estimado']} | salario {a['salario_anual']} | "
                      f"presupuesto restante {a['presupuesto_restante']} | "
                      f"margen salarial restante {a['margen_salarial_restante']}")
                print(f"   Scout: {c['justificacion']}")
                if c.get("comentario"):
                    print(f"   Financial: {c['comentario']}")
            decision = input("\nEscribe el id del jugador a fichar, 'nueva' (o 'nueva: más jóvenes') "
                             "para otra ronda de scouting, o 'salir': ")

        resultado = app.invoke(Command(resume=decision), config)

    print("\nPrioridades confirmadas:", resultado.get("prioridades_confirmadas"))
    print("\n=== RESULTADO DEL HITO ===")
    objetivo = resultado.get("jugador_objetivo")
    if objetivo:
        print(f"Jugador objetivo: {objetivo['nombre']} ({objetivo['posicion']}, {objetivo['edad']} años, "
              f"{objetivo['club']}), rating {objetivo['rating']}")
        print(f"Listo para iniciar la negociación (siguiente hito).")
    else:
        print("No se eligió ningún jugador objetivo.")

    print()
    print(app.get_graph().draw_mermaid())