"""Manager Agent: perfila la plantilla y entrega el diagnóstico con las posiciones prioritarias."""
import json

from llm import consultar_json
from registro import emitir

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


def perfilar_plantilla(estado):
    """Nodo de código: resume la plantilla por posición (cantidad, edad media, mejor rating, contratos por vencer)."""
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


def validar_nombres(diagnostico, plantilla):
    """Elimina jugadores que el modelo mencionó pero que no existen en la plantilla."""
    nombres = {j["nombre"] for j in plantilla}
    validos = []
    for item in diagnostico.get("jugadores_prescindibles", []):
        if item.get("nombre") in nombres:
            validos.append(item)
        else:
            emitir("aviso", f"El Manager Agent mencionó un jugador inexistente: {item.get('nombre')}",
                   agente="manager")
    diagnostico["jugadores_prescindibles"] = validos
    return diagnostico


def diagnosticar(estado):
    """Nodo del Manager Agent: el modelo diagnostica la plantilla y el código valida los nombres."""
    emitir("agente", "Manager Agent analizando la plantilla", agente="manager")
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
    diagnostico = consultar_json(SISTEMA_MANAGER, json.dumps(datos, ensure_ascii=False), agente="manager")
    diagnostico = validar_nombres(diagnostico, estado["plantilla"])
    emitir("info", "Diagnóstico listo", agente="manager", diagnostico=diagnostico)
    return {"diagnostico": diagnostico}


# ------------------------------------------------------------- CONSEJO EN NEGOCIACIÓN
SISTEMA_CONSEJO_MANAGER = """Eres el Manager Agent de {club}. El director deportivo está negociando el fichaje de
{jugador} y te pide tu opinión DEPORTIVA (el Financial Agent opina sobre el dinero por separado).

Recibirás en JSON el aporte del jugador a la plantilla (tipo de fichaje, rating frente al mejor actual,
edad, potencial), la última exigencia del vendedor, la última oferta propia y las rondas que quedan.
No conoces el precio mínimo del vendedor: no lo inventes.

En 2 o 3 frases y sin listas: di si deportivamente vale la pena insistir, mantener la postura o
retirarse, y por qué. Habla como un entrenador, no como una planilla: prefiere expresiones ("tiene un
futuro enorme", "nos daría profundidad en el medio") antes que ratings; usa como mucho un número.

Responde SOLO con un objeto JSON: {{"consejo": "..."}}"""


def aconsejar(club, jugador, contexto):
    """Consejo deportivo del Manager Agent durante una negociación (o None si falla)."""
    sistema = SISTEMA_CONSEJO_MANAGER.format(club=club, jugador=jugador)
    try:
        return consultar_json(sistema, json.dumps(contexto, ensure_ascii=False), agente="manager")["consejo"]
    except Exception:
        emitir("aviso", "El Manager Agent no pudo dar su consejo.", agente="manager")
        return None
