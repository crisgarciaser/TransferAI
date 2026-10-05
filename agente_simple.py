import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from datos import obtener_plantilla, obtener_resumen_club, buscar_jugadores

load_dotenv()

client = OpenAI(
    api_key=os.getenv("QWEN_API_KEY"),
    base_url=os.getenv("QWEN_BASE_URL"),
)
MODELO = os.getenv("QWEN_MODEL")

# 1) El menú de herramientas que Qwen puede pedir
HERRAMIENTAS = [
    {
        "type": "function",
        "function": {
            "name": "obtener_resumen_club",
            "description": "Devuelve presupuesto de fichajes, tope salarial, masa salarial actual y margen salarial de un club.",
            "parameters": {
                "type": "object",
                "properties": {"club": {"type": "string", "description": "Nombre exacto del club"}},
                "required": ["club"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_plantilla",
            "description": "Devuelve la lista de jugadores de un club con edad, posición, valor, salario, años de contrato y rating.",
            "parameters": {
                "type": "object",
                "properties": {"club": {"type": "string", "description": "Nombre exacto del club"}},
                "required": ["club"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_jugadores",
            "description": "Busca jugadores de otros clubes por posición, con filtros opcionales. Ordena por rating descendente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "posicion": {"type": "string", "description": "Código: POR, DFC, LAT, MED, EXT o DEL"},
                    "edad_max": {"type": "integer", "description": "Edad máxima del jugador"},
                    "valor_max": {"type": "number", "description": "Valor de mercado máximo, en millones de euros"},
                    "excluir_club": {"type": "string", "description": "Club a excluir de la búsqueda"},
                },
                "required": ["posicion"],
            },
        },
    },
]

# 2) La conexión entre el nombre que pide Qwen y la función real de Python
FUNCIONES = {
    "obtener_resumen_club": obtener_resumen_club,
    "obtener_plantilla": obtener_plantilla,
    "buscar_jugadores": buscar_jugadores,
}

SISTEMA = (
    "Eres el Manager Agent de un club de fútbol. Ayudas al director deportivo "
    "a decidir fichajes. Usa SIEMPRE las herramientas para obtener datos del "
    "club y de los jugadores; nunca inventes cifras ni nombres. Responde en "
    "español, de forma concisa y fundamentada en los datos obtenidos."
)


def ejecutar_agente(pregunta, max_pasos=6):
    mensajes = [
        {"role": "system", "content": SISTEMA},
        {"role": "user", "content": pregunta},
    ]

    for paso in range(1, max_pasos + 1):
        print(f"\n--- Paso {paso}: PENSAR ---")
        respuesta = client.chat.completions.create(
            model=MODELO,
            messages=mensajes,
            tools=HERRAMIENTAS,
        )
        mensaje = respuesta.choices[0].message

        # Si no pide herramientas, esta es la respuesta final
        if not mensaje.tool_calls:
            print("\n=== RESPUESTA FINAL ===")
            print(mensaje.content)
            return mensaje.content

        # Guardamos lo que Qwen dijo, para que "recuerde" su propia petición
        mensajes.append(mensaje.model_dump(exclude_none=True))

        for llamada in mensaje.tool_calls:
            nombre = llamada.function.name
            argumentos = json.loads(llamada.function.arguments)
            print(f"ACTUAR: {nombre}({argumentos})")

            resultado = FUNCIONES[nombre](**argumentos)
            print(f"OBSERVAR: la herramienta devolvió datos")

            mensajes.append(
                {
                    "role": "tool",
                    "tool_call_id": llamada.id,
                    "content": json.dumps(resultado, ensure_ascii=False),
                }
            )

    print("Se alcanzó el máximo de pasos sin respuesta final.")


if __name__ == "__main__":
    ejecutar_agente(
        "Soy el director deportivo del Deportivo Mirador. Quiero reforzar la "
        "defensa central. Analiza mi plantilla y mi presupuesto, y recomiéndame "
        "dos candidatos de otros clubes con su justificación."
    )