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