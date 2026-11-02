"""Filtra los CSV originales de EA Sports FC 24 para subirlos al repositorio.

Entrada : datos_originales/male_players.csv y datos_originales/male_teams.csv
          (archivos completos de Kaggle, muy pesados para GitHub)
Salida  : datos_fuente/male_players_fc24_top5.csv y datos_fuente/male_teams_fc24_top5.csv
          (solo FC 24, ultima actualizacion y las cinco grandes ligas; se conservan todas las columnas)

Uso: python filtrar_originales.py
"""
import csv
import sys
from pathlib import Path

RAIZ = Path(__file__).parent
ORIGEN = RAIZ / "datos_originales"
DESTINO = RAIZ / "datos_fuente"

VERSION = 24
LIGAS_ID = {13, 53, 31, 19, 16}  # Premier League, LaLiga, Serie A, Bundesliga, Ligue 1

csv.field_size_limit(10_000_000)  # algunas columnas de texto son largas


def a_numero(texto):
    try:
        return float(texto)
    except (TypeError, ValueError):
        return None


def leer_version(archivo):
    """Devuelve las columnas y las filas de la version 24 en su ultima actualizacion."""
    with open(archivo, encoding="utf-8", newline="") as f:
        lector = csv.DictReader(f)
        filas = [fila for fila in lector if a_numero(fila["fifa_version"]) == VERSION]
        columnas = lector.fieldnames
    if not filas:
        sys.exit(f"No se encontraron filas de la version {VERSION} en {archivo.name}.")
    ultima = max(a_numero(fila["fifa_update"]) or 0 for fila in filas)
    filas = [fila for fila in filas if (a_numero(fila["fifa_update"]) or 0) == ultima]
    return columnas, filas


def guardar(nombre, columnas, filas):
    DESTINO.mkdir(exist_ok=True)
    with open(DESTINO / nombre, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=columnas)
        escritor.writeheader()
        escritor.writerows(filas)
    tamano_mb = (DESTINO / nombre).stat().st_size / 1_000_000
    print(f"  {nombre}: {len(filas)} filas, {tamano_mb:.1f} MB")


def main():
    for nombre in ("male_players.csv", "male_teams.csv"):
        if not (ORIGEN / nombre).exists():
            sys.exit(f"Falta datos_originales/{nombre}. Revisa que el archivo este en esa carpeta.")

    print("Leyendo equipos...")
    col_equipos, equipos = leer_version(ORIGEN / "male_teams.csv")
    equipos = [e for e in equipos
               if a_numero(e["league_id"]) in LIGAS_ID and a_numero(e["league_level"]) == 1]
    ids_equipos = {int(a_numero(e["team_id"])) for e in equipos}

    print("Leyendo jugadores (puede tardar un poco)...")
    col_jugadores, jugadores = leer_version(ORIGEN / "male_players.csv")
    jugadores = [j for j in jugadores
                 if a_numero(j["club_team_id"]) is not None
                 and int(a_numero(j["club_team_id"])) in ids_equipos]

    print("Archivos creados en datos_fuente/:")
    guardar("male_teams_fc24_top5.csv", col_equipos, equipos)
    guardar("male_players_fc24_top5.csv", col_jugadores, jugadores)


if __name__ == "__main__":
    main()