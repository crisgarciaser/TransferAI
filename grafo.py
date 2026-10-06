import json
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from datos import cargar_jugadores, obtener_plantilla, obtener_resumen_club
from herramientas import FUNCIONES_SCOUTING, HERRAMIENTAS_SCOUTING
from llm import consultar_json, ejecutar_con_herramientas, extraer_json

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt

class Estado(TypedDict, total=False):
    club: str
    resumen: dict
    plantilla: list
    perfil_posiciones: dict
    diagnostico: dict
    prioridades_confirmadas: list
    lista_corta: list

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

POSICIONES_VALIDAS = {"POR", "DFC", "LAT", "MED", "EXT", "DEL"}


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

Responde SOLO con un objeto JSON con esta forma exacta:
{"lista_corta": [{"id": 27, "posicion": "DFC", "justificacion": "..."}]}"""


def validar_candidatos(candidatos, club, prioridades):
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
    contexto = {
        "club": club,
        "presupuesto_fichajes": estado["resumen"]["presupuesto_fichajes"],
        "posiciones_prioritarias": prioridades,
        "perfil_posiciones": {p: estado["perfil_posiciones"].get(p) for p in prioridades},
    }
    print("\n--- Scouting Agent trabajando ---")
    texto = ejecutar_con_herramientas(
        SISTEMA_SCOUT,
        json.dumps(contexto, ensure_ascii=False),
        HERRAMIENTAS_SCOUTING,
        FUNCIONES_SCOUTING,
    )
    if texto is None:
        print("AVISO: el Scouting Agent no llegó a una respuesta final.")
        return {"lista_corta": []}
    try:
        propuestos = extraer_json(texto).get("lista_corta", [])
    except json.JSONDecodeError:
        print("AVISO: respuesta del Scouting Agent no era un JSON válido:\n", texto)
        return {"lista_corta": []}
    return {"lista_corta": validar_candidatos(propuestos, club, prioridades)}

constructor = StateGraph(Estado)
constructor.add_node("cargar_club", cargar_club)
constructor.add_node("perfilar_plantilla", perfilar_plantilla)
constructor.add_node("diagnosticar", diagnosticar)
constructor.add_node("confirmar_prioridades", confirmar_prioridades)
constructor.add_node("hacer_scouting", hacer_scouting)
constructor.add_edge(START, "cargar_club")
constructor.add_edge("cargar_club", "perfilar_plantilla")
constructor.add_edge("perfilar_plantilla", "diagnosticar")
constructor.add_edge("diagnosticar", "confirmar_prioridades")
constructor.add_edge("confirmar_prioridades", "hacer_scouting")
constructor.add_edge("hacer_scouting", END)

app = constructor.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "sesion-1"}}

    resultado = app.invoke({"club": "Deportivo Mirador"}, config)

    if "__interrupt__" in resultado:
        propuestas = resultado["__interrupt__"][0].value["propuestas"]
        print("\n=== PROPUESTA DEL MANAGER AGENT ===")
        for p in propuestas:
            print(f"- {p['posicion']} (urgencia {p['urgencia']}): {p['motivo']}")
        print("\nPosiciones válidas: POR, DFC, LAT, MED, EXT, DEL")
        decision = input("¿Qué posiciones quieres priorizar? (separa con comas, ej: DFC,MED): ")
        resultado = app.invoke(Command(resume=decision), config)

    print("\nPrioridades confirmadas:", resultado["prioridades_confirmadas"])

    print("\n=== LISTA CORTA DEL SCOUTING AGENT ===")
    if not resultado["lista_corta"]:
        print("Sin candidatos.")
    for c in resultado["lista_corta"]:
        print(f"- [{c['posicion']}] {c['nombre']} ({c['edad']} años, {c['club']}) "
              f"rating {c['rating']}, valor {c['valor_mercado']}, salario {c['salario_anual']}")
        print(f"  {c['justificacion']}")

    print()
    print(app.get_graph().draw_mermaid())