import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("QWEN_API_KEY"),
    base_url=os.getenv("QWEN_BASE_URL"),
)
MODELO = os.getenv("QWEN_MODEL")


def consultar_json(sistema, usuario):
    """Envía una consulta a Qwen y devuelve su respuesta como diccionario."""
    respuesta = client.chat.completions.create(
        model=MODELO,
        messages=[
            {"role": "system", "content": sistema},
            {"role": "user", "content": usuario},
        ],
        temperature=0.2,
    )
    texto = respuesta.choices[0].message.content
    inicio, fin = texto.find("{"), texto.rfind("}")
    try:
        return json.loads(texto[inicio : fin + 1])
    except json.JSONDecodeError:
        print("La respuesta del modelo no fue un JSON válido:\n", texto)
        raise

def extraer_json(texto):
    inicio, fin = texto.find("{"), texto.rfind("}")
    return json.loads(texto[inicio : fin + 1])


def ejecutar_con_herramientas(sistema, usuario, herramientas, funciones, max_pasos=8):
    """Ciclo Pensar-Actuar-Observar. Devuelve el texto final del modelo (o None)."""
    mensajes = [
        {"role": "system", "content": sistema},
        {"role": "user", "content": usuario},
    ]
    for _ in range(max_pasos):
        respuesta = client.chat.completions.create(
            model=MODELO,
            messages=mensajes,
            tools=herramientas,
            temperature=0.2,
        )
        mensaje = respuesta.choices[0].message

        if not mensaje.tool_calls:
            return mensaje.content

        mensajes.append(mensaje.model_dump(exclude_none=True))
        for llamada in mensaje.tool_calls:
            nombre = llamada.function.name
            try:
                argumentos = json.loads(llamada.function.arguments)
                print(f"  ACTUAR: {nombre}({argumentos})")
                resultado = funciones[nombre](**argumentos)
            except Exception as error:
                resultado = {"error": str(error)}
                print(f"  ERROR en {nombre}: {error}")
            mensajes.append(
                {
                    "role": "tool",
                    "tool_call_id": llamada.id,
                    "content": json.dumps(resultado, ensure_ascii=False),
                }
            )
    return None