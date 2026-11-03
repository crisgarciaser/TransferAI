import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from config import AGENTES_CON_RAZONAMIENTO, MAX_PASOS_HERRAMIENTAS, TEMPERATURA
from registro import emitir

load_dotenv()

client = OpenAI(
    api_key=os.getenv("QWEN_API_KEY"),
    base_url=os.getenv("QWEN_BASE_URL"),
)
MODELO = os.getenv("QWEN_MODEL")
_control_razonamiento = True   # pasa a False si el proveedor no acepta el parámetro enable_thinking


def _crear(agente, **kwargs):
    """Llama al modelo activando o desactivando su razonamiento según AGENTES_CON_RAZONAMIENTO.
    Si el proveedor rechaza el parámetro, se reintenta sin él y no se vuelve a enviar."""
    global _control_razonamiento
    if _control_razonamiento:
        try:
            return client.chat.completions.create(
                model=MODELO, temperature=TEMPERATURA,
                extra_body={"enable_thinking": agente in AGENTES_CON_RAZONAMIENTO}, **kwargs)
        except Exception as error:
            if "enable_thinking" not in str(error) and "thinking" not in str(error).lower():
                raise
            _control_razonamiento = False
            emitir("aviso", "El proveedor no permite controlar el razonamiento del modelo; se usa su configuración por defecto.")
    return client.chat.completions.create(model=MODELO, temperature=TEMPERATURA, **kwargs)


def _registrar_llamada(agente, respuesta):
    """Guarda en el log qué agente llamó al modelo y cuántos tokens usó."""
    uso = getattr(respuesta, "usage", None)
    emitir("llm", agente=agente, modelo=MODELO,
           tokens_entrada=getattr(uso, "prompt_tokens", None),
           tokens_salida=getattr(uso, "completion_tokens", None))


def extraer_json(texto):
    """Recorta el texto desde la primera '{' hasta la última '}' y lo convierte en diccionario.
    Si el modelo olvidó cerrar el JSON (pasa sin razonamiento), intenta completarlo."""
    inicio, fin = texto.find("{"), texto.rfind("}")
    try:
        return json.loads(texto[inicio : fin + 1])
    except json.JSONDecodeError:
        recorte = texto[inicio:].rstrip()
        for cierre in ("}", '"}', '"}}', "}}"):
            try:
                return json.loads(recorte + cierre)
            except json.JSONDecodeError:
                continue
        raise


def consultar_json(sistema, usuario, agente="modelo"):
    """Envía una consulta al modelo y devuelve su respuesta como diccionario."""
    respuesta = _crear(agente, messages=[
        {"role": "system", "content": sistema},
        {"role": "user", "content": usuario},
    ])
    _registrar_llamada(agente, respuesta)
    texto = respuesta.choices[0].message.content
    try:
        return extraer_json(texto)
    except json.JSONDecodeError:
        emitir("error", f"La respuesta del {agente} no fue un JSON válido.", respuesta=texto)
        raise


def ejecutar_con_herramientas(sistema, usuario, herramientas, funciones, agente="modelo"):
    """Ciclo Pensar-Actuar-Observar. Devuelve el texto final del modelo (o None)."""
    mensajes = [
        {"role": "system", "content": sistema},
        {"role": "user", "content": usuario},
    ]
    for _ in range(MAX_PASOS_HERRAMIENTAS):
        respuesta = _crear(agente, messages=mensajes, tools=herramientas)
        _registrar_llamada(agente, respuesta)
        mensaje = respuesta.choices[0].message

        if not mensaje.tool_calls:
            return mensaje.content

        mensajes.append(mensaje.model_dump(exclude_none=True))
        for llamada in mensaje.tool_calls:
            nombre = llamada.function.name
            try:
                argumentos = json.loads(llamada.function.arguments)
                emitir("herramienta", f"{nombre}({argumentos})", agente=agente,
                       herramienta=nombre, argumentos=argumentos)
                resultado = funciones[nombre](**argumentos)
            except Exception as error:
                resultado = {"error": str(error)}
                emitir("error", f"Error en {nombre}: {error}", agente=agente)
            mensajes.append(
                {
                    "role": "tool",
                    "tool_call_id": llamada.id,
                    "content": json.dumps(resultado, ensure_ascii=False),
                }
            )
    # Se agotaron los pasos: se pide una respuesta final con lo que ya encontró, sin más herramientas
    emitir("aviso", "El agente agotó sus pasos de búsqueda; se le pide cerrar con lo encontrado.", agente=agente)
    mensajes.append({"role": "user", "content": "Se acabaron tus búsquedas. Responde AHORA solo con el JSON final, "
                                                 "usando únicamente los jugadores que ya evaluaste."})
    respuesta = _crear(agente, messages=mensajes)
    _registrar_llamada(agente, respuesta)
    return respuesta.choices[0].message.content
