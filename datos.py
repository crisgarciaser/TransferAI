import csv
from pathlib import Path

CARPETA = Path(__file__).parent / "datos_reales"
EDAD_VETERANO = 30       # el mejor jugador actual se considera veterano desde esta edad
EDAD_JOVEN = 24          # un candidato es "joven" hasta esta edad
TOLERANCIA_RATING = 6    # un joven puede tener hasta estos puntos menos que el veterano

def _numero(texto):
    valor = float(texto)
    return int(valor) if valor.is_integer() else valor

def _leer_csv(nombre, campos_numericos):
    with open(CARPETA / nombre, encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    for fila in filas:
        for campo in campos_numericos:
            fila[campo] = _numero(fila[campo])
    return filas

def cargar_clubes():
    return _leer_csv("clubes.csv", ["nivel", "presupuesto_fichajes", "tope_salarial"])

def cargar_jugadores():
    return _leer_csv(
        "jugadores.csv",
        ["id", "edad", "valor_mercado", "salario_anual", "anios_contrato", "rating"],
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

def buscar_jugadores(posicion, edad_max=None, valor_max=None, excluir_club=None, max_resultados=10):
    resultado = [j for j in cargar_jugadores() if j["posicion"] == posicion]
    if edad_max is not None:
        resultado = [j for j in resultado if j["edad"] <= edad_max]
    if valor_max is not None:
        resultado = [j for j in resultado if j["valor_mercado"] <= valor_max]
    if excluir_club is not None:
        resultado = [j for j in resultado if j["club"] != excluir_club]
    resultado = sorted(resultado, key=lambda j: j["rating"], reverse=True)
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
    else:
        tipo = "no_aporta"

    return {
        "id": jugador["id"],
        "nombre": jugador["nombre"],
        "posicion": jugador["posicion"],
        "edad": jugador["edad"],
        "rating": jugador["rating"],
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
    traspaso = jugador["valor_mercado"]
    salario = jugador["salario_anual"]
    presupuesto = resumen["presupuesto_fichajes"]
    margen = resumen["margen_salarial"]

    uso_presupuesto = round(100 * traspaso / presupuesto, 1) if presupuesto > 0 else 100.0
    uso_margen = round(100 * salario / margen, 1) if margen > 0 else 100.0

    alertas = []
    if traspaso > presupuesto:
        alertas.append("el traspaso estimado supera el presupuesto de fichajes")
    if salario > margen:
        alertas.append("el salario supera el margen salarial disponible")

    if alertas:
        veredicto = "inviable"
    else:
        veredicto = "viable"
        if uso_presupuesto > 70:
            alertas.append(f"consume {uso_presupuesto}% del presupuesto de fichajes")
            veredicto = "ajustado"
        if uso_margen > 50:
            alertas.append(f"consume {uso_margen}% del margen salarial")
            veredicto = "ajustado"

    return {
        "veredicto": veredicto,
        "traspaso_estimado": traspaso,
        "salario_anual": salario,
        "presupuesto_restante": round(presupuesto - traspaso, 2),
        "margen_salarial_restante": round(margen - salario, 2),
        "masa_salarial_resultante": round(resumen["masa_salarial_actual"] + salario, 2),
        "uso_presupuesto_pct": uso_presupuesto,
        "uso_margen_pct": uso_margen,
        "alertas": alertas,
    }