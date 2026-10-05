import csv
from pathlib import Path

CARPETA = Path(__file__).parent / "datos"

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

def buscar_jugadores(posicion, edad_max=None, valor_max=None, excluir_club=None):
    resultado = [j for j in cargar_jugadores() if j["posicion"] == posicion]
    if edad_max is not None:
        resultado = [j for j in resultado if j["edad"] <= edad_max]
    if valor_max is not None:
        resultado = [j for j in resultado if j["valor_mercado"] <= valor_max]
    if excluir_club is not None:
        resultado = [j for j in resultado if j["club"] != excluir_club]
    return sorted(resultado, key=lambda j: j["rating"], reverse=True)