import json
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from datos import obtener_plantilla, obtener_resumen_club
from llm import consultar_json

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt

class Estado(TypedDict, total=False):
    club: str
    resumen: dict
    plantilla: list
    perfil_posiciones: dict
    diagnostico: dict
    prioridades_confirmadas: list

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

constructor = StateGraph(Estado)
constructor.add_node("cargar_club", cargar_club)
constructor.add_node("perfilar_plantilla", perfilar_plantilla)
constructor.add_node("diagnosticar", diagnosticar)
constructor.add_node("confirmar_prioridades", confirmar_prioridades)
constructor.add_edge(START, "cargar_club")
constructor.add_edge("cargar_club", "perfilar_plantilla")
constructor.add_edge("perfilar_plantilla", "diagnosticar")
constructor.add_edge("diagnosticar", "confirmar_prioridades")
constructor.add_edge("confirmar_prioridades", END)

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
    print()
    print(app.get_graph().draw_mermaid())