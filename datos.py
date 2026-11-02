import csv
from pathlib import Path

from config import (
    INTERVALO_SALARIO,
    INTERVALO_SALARIO_ESTRELLA,
    RATING_ESTRELLA,
    REPUTACION_ESTRELLA,
    EDAD_JOVEN,
    EDAD_PROMESA,
    EDAD_VETERANO,
    MARGEN_POTENCIAL,
    MAX_RESULTADOS_BUSQUEDA,
    TOLERANCIA_PROMESA,
    TOLERANCIA_RATING,
    UMBRAL_AJUSTADO_MARGEN,
    UMBRAL_AJUSTADO_PRESUPUESTO,
)

CARPETA = Path(__file__).parent / "datos_reales"


def _numero(texto):
    if texto in ("", None):
        return None  # dato no disponible (por ejemplo, jugadores sin valor de Transfermarkt)
    valor = float(texto)
    return int(valor) if valor.is_integer() else valor

def _leer_csv(nombre, campos_numericos):
    with open(CARPETA / nombre, encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    for fila in filas:
        for campo in campos_numericos:
            fila[campo] = _numero(fila[campo])
    return filas

# ======================================================================
# DATOS EN MEMORIA Y CAMBIOS DE LA PARTIDA
# Los CSV se leen una sola vez. Los fichajes y ventas de la partida se guardan aparte
# (_traspasos y _ajustes_presupuesto) y se aplican encima cada vez que se consultan los datos,
# así el scouting, la plantilla y el diagnóstico ven siempre el mercado actualizado.
# ======================================================================
_cache = {}
_traspasos = {}            # id del jugador -> cambios (club, salario_anual, anios_contrato, titular)
_ajustes_presupuesto = {}  # club -> suma de lo que gastó (negativo) o ingresó (positivo) en la ventana


def reiniciar_mercado():
    """Borra los cambios de la partida (se usa al empezar una sesión y en las pruebas)."""
    _traspasos.clear()
    _ajustes_presupuesto.clear()


def registrar_traspaso(id_jugador, nuevo_club, salario_anual, anios_contrato, titular="si"):
    _traspasos[int(id_jugador)] = {"club": nuevo_club, "salario_anual": round(salario_anual, 3),
                                   "anios_contrato": int(anios_contrato), "titular": titular,
                                   "cedido_por": ""}


def ajustar_presupuesto(club, monto):
    _ajustes_presupuesto[club] = round(_ajustes_presupuesto.get(club, 0) + monto, 2)


def es_estrella(jugador):
    return jugador["reputacion_internacional"] >= REPUTACION_ESTRELLA or jugador["rating"] >= RATING_ESTRELLA


def intervalo_salario(jugador):
    """Lo que el club comprador cree que gana el jugador: un intervalo que contiene el salario real.
    Los extremos dependen del id (siempre el mismo intervalo para el mismo jugador) y son más
    estrechos para las estrellas."""
    bajo, alto = INTERVALO_SALARIO_ESTRELLA if es_estrella(jugador) else INTERVALO_SALARIO
    r1, r2 = (jugador["id"] * 7919 % 101) / 100, (jugador["id"] * 104729 % 103) / 102
    real = jugador["salario_anual"]
    minimo = real * (bajo + (1 - bajo) * r1)
    maximo = real * (1 + (alto - 1) * r2)
    return round(minimo, 2), round(max(maximo, minimo + 0.01), 2)


def cargar_clubes():
    if "clubes" not in _cache:
        _cache["clubes"] = _leer_csv_clubes()
    clubes = []
    for c in _cache["clubes"]:
        c = dict(c)
        c["presupuesto_fichajes"] = round(c["presupuesto_fichajes"] + _ajustes_presupuesto.get(c["club"], 0), 2)
        clubes.append(c)
    return clubes


def cargar_jugadores():
    if "jugadores" not in _cache:
        _cache["jugadores"] = _leer_csv_jugadores()
    return [{**j, **_traspasos.get(j["id"], {})} for j in _cache["jugadores"]]


def _leer_csv_clubes():
    return _leer_csv(
        "clubes.csv",
        ["nivel", "presupuesto_fichajes", "tope_salarial", "rating_club", "ataque",
         "mediocampo", "defensa", "prestigio_domestico", "rank_ataque", "rank_mediocampo",
         "rank_defensa", "n_clubes_liga", "edad_media", "valor_plantilla", "anchura_ofensiva",
         "profundidad_defensiva", "jugadores_en_area", "posicion_22_23", "puntos_por_partido_22_23",
         "aforo_estadio", "balance_traspasos"],
    )

def _leer_csv_jugadores():
    return _leer_csv(
        "jugadores.csv",
        ["id", "edad", "valor_mercado", "salario_anual", "anios_contrato", "rating",
         "potencial", "reputacion_internacional", "clausula_rescision", "valor_ea", "valor_tm",
         "valor_max_tm", "altura", "at_ritmo", "at_tiro", "at_pase", "at_regate", "at_defensa",
         "at_fisico", "at_cabezazo", "at_vision", "at_resistencia", "at_porteria"],
    )

def obtener_plantilla(club):
    return [j for j in cargar_jugadores() if j["club"] == club]

def obtener_resumen_club(club):
    fila = next(c for c in cargar_clubes() if c["club"] == club)
    plantilla = obtener_plantilla(club)
    masa = sum(j["salario_anual"] for j in plantilla)
    return {
        "club": club,
        "nivel": fila["nivel"],
        "presupuesto_fichajes": fila["presupuesto_fichajes"],
        "tope_salarial": fila["tope_salarial"],
        "masa_salarial_actual": round(masa, 2),
        "margen_salarial": round(fila["tope_salarial"] - masa, 2),
        "competicion_internacional": fila["competicion_internacional"],
        "n_jugadores": len(plantilla),
    }

def buscar_jugadores(posicion, edad_max=None, valor_max=None, excluir_club=None, max_resultados=MAX_RESULTADOS_BUSQUEDA,
                     edad_min=None, rating_min=None, rating_max=None, potencial_min=None,
                     ordenar_por="rating"):
    # Los jugadores cedidos no se pueden comprar a su club actual: no aparecen en el scouting
    resultado = [j for j in cargar_jugadores() if j["posicion"] == posicion and not j.get("cedido_por")]
    if edad_max is not None:
        resultado = [j for j in resultado if j["edad"] <= edad_max]
    if edad_min is not None:
        resultado = [j for j in resultado if j["edad"] >= edad_min]
    if valor_max is not None:
        resultado = [j for j in resultado if j["valor_mercado"] <= valor_max]
    if excluir_club is not None:
        resultado = [j for j in resultado if j["club"] != excluir_club]
    if rating_min is not None:
        resultado = [j for j in resultado if j["rating"] >= rating_min]
    if rating_max is not None:
        resultado = [j for j in resultado if j["rating"] <= rating_max]
    if potencial_min is not None:
        resultado = [j for j in resultado if j["potencial"] >= potencial_min]
    if ordenar_por == "potencial":
        clave = lambda j: (j["potencial"], j["rating"])
    else:
        # Solo rating: en empates se conserva el orden original (compatibilidad hacia atrás)
        clave = lambda j: j["rating"]
    resultado = sorted(resultado, key=clave, reverse=True)
    return resultado[:max_resultados]

def evaluar_encaje(id_jugador, club):
    try:
        id_jugador = int(id_jugador)
    except (TypeError, ValueError):
        return {"error": "id_jugador debe ser un número entero"}

    jugador = next((j for j in cargar_jugadores() if j["id"] == id_jugador), None)
    if jugador is None:
        return {"error": f"No existe un jugador con id {id_jugador}"}

    clubes = {c["club"]: c for c in cargar_clubes()}
    if club not in clubes:
        return {"error": f"No existe el club {club}"}

    propios = [j for j in obtener_plantilla(club) if j["posicion"] == jugador["posicion"]]
    mejor = max(propios, key=lambda j: j["rating"], default=None)
    mejor_rating = mejor["rating"] if mejor else 0
    edad_mejor = mejor["edad"] if mejor else None
    mejora = jugador["rating"] - mejor_rating

    if mejora > 0:
        tipo = "mejora_inmediata"
    elif (mejor is not None
          and edad_mejor >= EDAD_VETERANO
          and jugador["edad"] <= EDAD_JOVEN
          and mejora >= -TOLERANCIA_RATING):
        tipo = "sucesor_joven"
    elif (jugador["edad"] <= EDAD_PROMESA
          and jugador["potencial"] >= mejor_rating + MARGEN_POTENCIAL
          and mejora >= -TOLERANCIA_PROMESA):
        tipo = "promesa"
    else:
        tipo = "no_aporta"

    return {
        "id": jugador["id"],
        "nombre": jugador["nombre"],
        "posicion": jugador["posicion"],
        "edad": jugador["edad"],
        "rating": jugador["rating"],
        "potencial": jugador["potencial"],
        "club_actual": jugador["club"],
        "es_titular_en_su_club": jugador["titular"] == "si",
        "anios_contrato": jugador["anios_contrato"],
        "nivel_club_actual": clubes[jugador["club"]]["nivel"],
        "nivel_tu_club": clubes[club]["nivel"],
        "mejor_rating_actual_en_tu_club": mejor_rating,
        "edad_del_mejor_actual": edad_mejor,
        "mejora_sobre_el_mejor_actual": mejora,
        "tipo_de_fichaje": tipo,
    }

def analizar_viabilidad(jugador, resumen):
    """Viabilidad económica de un candidato. El salario real es privado: se usa el intervalo estimado.
    Veredictos: viable, ajustado, incierto (el intervalo cruza el margen salarial) o inviable."""
    traspaso = jugador["valor_mercado"]
    salario_min, salario_max = intervalo_salario(jugador)
    presupuesto = resumen["presupuesto_fichajes"]
    margen = resumen["margen_salarial"]

    uso_presupuesto = round(100 * traspaso / presupuesto, 1) if presupuesto > 0 else 100.0
    uso_margen = round(100 * salario_max / margen, 1) if margen > 0 else 100.0

    alertas = []
    if traspaso > presupuesto:
        alertas.append("el traspaso estimado supera el presupuesto de fichajes")
    if salario_min > margen:
        alertas.append("incluso el salario estimado más bajo supera el margen salarial disponible")

    if alertas:
        veredicto = "inviable"
    elif salario_max > margen:
        veredicto = "incierto"
        alertas.append(f"el salario estimado ({salario_min}-{salario_max}) podría superar el margen salarial")
    else:
        veredicto = "viable"
        if uso_presupuesto > UMBRAL_AJUSTADO_PRESUPUESTO:
            alertas.append(f"consume {uso_presupuesto}% del presupuesto de fichajes")
            veredicto = "ajustado"
        if uso_margen > UMBRAL_AJUSTADO_MARGEN:
            alertas.append(f"consume hasta {uso_margen}% del margen salarial")
            veredicto = "ajustado"

    return {
        "veredicto": veredicto,
        "traspaso_estimado": traspaso,
        "salario_estimado_min": salario_min,
        "salario_estimado_max": salario_max,
        "presupuesto_restante": round(presupuesto - traspaso, 2),
        "margen_salarial_restante_peor_caso": round(margen - salario_max, 2),
        "uso_presupuesto_pct": uso_presupuesto,
        "uso_margen_max_pct": uso_margen,
        "alertas": alertas,
    }
