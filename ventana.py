"""Ventana de fichajes: calendario de eventos futuros y bandeja de mensajes."""
from config import DIAS_VENTANA


def programar(calendario, dia_actual, dias_de_espera, tipo, asunto, datos=None):
    """Agrega un evento al calendario dentro de 'dias_de_espera' días. Devuelve el calendario nuevo."""
    nuevo_id = 1 + max((e["id"] for e in calendario), default=0)
    evento = {"id": nuevo_id, "dia": dia_actual + dias_de_espera, "tipo": tipo,
              "asunto": asunto, "datos": datos or {}}
    return sorted(calendario + [evento], key=lambda e: (e["dia"], e["id"]))


def avanzar(dia_actual, dias, calendario, bandeja):
    """Avanza 'dias' días. Los eventos que vencen pasan del calendario a la bandeja.

    Devuelve (dia_nuevo, calendario_restante, bandeja_nueva, llegados, ventana_cerrada).
    La ventana se cierra cuando se pasa del día DIAS_VENTANA.
    """
    dias = max(1, int(dias))
    dia_nuevo = dia_actual + dias
    cerrada = dia_nuevo > DIAS_VENTANA
    dia_nuevo = min(dia_nuevo, DIAS_VENTANA)

    llegados = [e for e in calendario if e["dia"] <= dia_nuevo]
    restante = [e for e in calendario if e["dia"] > dia_nuevo]
    bandeja_nueva = bandeja + [{**e, "leido": False} for e in llegados]
    return dia_nuevo, restante, bandeja_nueva, llegados, cerrada


def no_leidos(bandeja):
    return [m for m in bandeja if not m["leido"]]


def marcar_leidos(bandeja):
    return [{**m, "leido": True} for m in bandeja]


def leer_comando(texto):
    """Interpreta lo que escribe el usuario en el centro de mando.

    1 ver plantilla | 2 ver estado del club | 3 revisar bandeja | 4 buscar refuerzos | 5 fichajes  | 6 ventas
    7 avanzar días ('6' = un día, '6 5' = cinco) | 8 cerrar el mercado | otro -> ("invalido", None)
    También acepta las palabras: plantilla, estado, bandeja, buscar, fichajes, ventas, avanzar 5, cerrar.
    """
    partes = str(texto).strip().lower().split()
    if not partes:
        return "invalido", None
    comandos = {"1": "plantilla", "plantilla": "plantilla", "2": "estado", "estado": "estado",
                "3": "bandeja", "bandeja": "bandeja", "4": "buscar", "buscar": "buscar",
                "5": "fichajes", "fichajes": "fichajes", "6": "ventas", "ventas": "ventas",
                "7": "avanzar", "avanzar": "avanzar", "8": "cerrar", "cerrar": "cerrar"}
    comando = comandos.get(partes[0], "invalido")
    if comando == "avanzar":
        try:
            dias = int(partes[1]) if len(partes) > 1 else 1
        except ValueError:
            return "invalido", None
        return ("avanzar", dias) if dias >= 1 else ("invalido", None)
    return comando, None
