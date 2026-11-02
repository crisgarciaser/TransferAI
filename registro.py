"""Registro de eventos de TransferAI.

Los agentes y nodos no imprimen en pantalla: emiten eventos con emitir(). Cada evento
1) se guarda en un archivo logs/sesion_<fecha>.jsonl (trazabilidad de la sesión) y
2) se entrega a las interfaces suscritas (hoy la terminal; más adelante, la página HTML).

Tipos de evento usados: info, aviso, error, agente, herramienta, descarte, plantilla, llm.
"""
import json
from datetime import datetime
from pathlib import Path

CARPETA_LOGS = Path(__file__).parent / "logs"

_oyentes = []        # funciones que reciben cada evento (la interfaz se suscribe aquí)
_archivo_log = None  # archivo de la sesión actual


def iniciar_sesion():
    """Crea el archivo de log de una nueva sesión y devuelve su ruta."""
    global _archivo_log
    CARPETA_LOGS.mkdir(exist_ok=True)
    _archivo_log = CARPETA_LOGS / f"sesion_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    return _archivo_log


def suscribir(funcion):
    """Registra una función que recibirá cada evento emitido."""
    _oyentes.append(funcion)


def emitir(tipo, mensaje="", **datos):
    """Registra un evento en el log y lo entrega a las interfaces suscritas."""
    evento = {"hora": datetime.now().isoformat(timespec="seconds"), "tipo": tipo,
              "mensaje": mensaje, "datos": datos}
    if _archivo_log is not None:
        with open(_archivo_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(evento, ensure_ascii=False, default=str) + "\n")
    for oyente in _oyentes:
        oyente(evento)
    return evento
