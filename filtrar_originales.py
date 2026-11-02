"""Filtra los CSV originales (EA Sports FC 24 y Transfermarkt) para subirlos al repositorio.

Entrada (archivos completos de Kaggle, muy pesados para GitHub):
    datos_originales/male_players.csv, male_teams.csv, male_coaches.csv   (EA Sports FC 24)
    datos_originales/transfermarkt/players.csv, clubs.csv, games.csv      (Transfermarkt)
Salida (livianos, se suben a GitHub):
    datos_fuente/male_players_fc24_top5.csv, male_teams_fc24_top5.csv, male_coaches_fc24_top5.csv
    datos_fuente/tm_jugadores.csv, tm_clubes.csv, tm_partidos_22_23.csv

Uso: python filtrar_originales.py
Los archivos de Transfermarkt y de entrenadores son opcionales: si no estan, se omiten.
"""
import csv
import sys
from pathlib import Path

RAIZ = Path(__file__).parent
ORIGEN = RAIZ / "datos_originales"
ORIGEN_TM = ORIGEN / "transfermarkt"
DESTINO = RAIZ / "datos_fuente"

VERSION = 24
LIGAS_ID = {13, 53, 31, 19, 16}            # EA: Premier League, LaLiga, Serie A, Bundesliga, Ligue 1
LIGAS_TM = {"GB1", "ES1", "IT1", "L1", "FR1"}  # Transfermarkt: las mismas cinco ligas
TEMPORADA_TM = 2022                         # temporada 2022/23, la anterior a EA FC 24
TEMPORADA_MIN_JUGADORES_TM = 2020           # jugadores de TM activos desde esta temporada

COLUMNAS_TM_JUGADORES = ["player_id", "name", "last_name", "date_of_birth", "country_of_citizenship",
                         "current_club_id", "current_club_name", "last_season", "market_value_in_eur",
                         "highest_market_value_in_eur", "contract_expiration_date", "agent_name",
                         "height_in_cm", "foot"]
COLUMNAS_TM_CLUBES = ["club_id", "club_code", "name", "domestic_competition_id", "stadium_name",
                      "stadium_seats", "net_transfer_record", "last_season"]
COLUMNAS_TM_PARTIDOS = ["game_id", "competition_id", "season", "round", "date", "home_club_id",
                        "away_club_id", "home_club_goals", "away_club_goals", "home_club_name",
                        "away_club_name"]

csv.field_size_limit(10_000_000)  # algunas columnas de texto son largas


def a_numero(texto):
    try:
        return float(texto)
    except (TypeError, ValueError):
        return None


def leer(archivo):
    with open(archivo, encoding="utf-8", newline="") as f:
        lector = csv.DictReader(f)
        return lector.fieldnames, list(lector)


def leer_version(archivo):
    """Devuelve las columnas y las filas de la version 24 en su ultima actualizacion."""
    columnas, filas = leer(archivo)
    filas = [fila for fila in filas if a_numero(fila["fifa_version"]) == VERSION]
    if not filas:
        sys.exit(f"No se encontraron filas de la version {VERSION} en {archivo.name}.")
    ultima = max(a_numero(fila["fifa_update"]) or 0 for fila in filas)
    filas = [fila for fila in filas if (a_numero(fila["fifa_update"]) or 0) == ultima]
    return columnas, filas


def guardar(nombre, columnas, filas):
    DESTINO.mkdir(exist_ok=True)
    with open(DESTINO / nombre, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(filas)
    tamano_mb = (DESTINO / nombre).stat().st_size / 1_000_000
    print(f"  {nombre}: {len(filas)} filas, {tamano_mb:.1f} MB")


def filtrar_ea():
    for nombre in ("male_players.csv", "male_teams.csv"):
        if not (ORIGEN / nombre).exists():
            sys.exit(f"Falta datos_originales/{nombre}. Revisa que el archivo este en esa carpeta.")

    print("EA Sports FC 24: leyendo equipos...")
    col_equipos, equipos = leer_version(ORIGEN / "male_teams.csv")
    equipos = [e for e in equipos
               if a_numero(e["league_id"]) in LIGAS_ID and a_numero(e["league_level"]) == 1]
    ids_equipos = {int(a_numero(e["team_id"])) for e in equipos}

    print("EA Sports FC 24: leyendo jugadores (puede tardar un poco)...")
    col_jugadores, jugadores = leer_version(ORIGEN / "male_players.csv")
    jugadores = [j for j in jugadores
                 if a_numero(j["club_team_id"]) is not None
                 and int(a_numero(j["club_team_id"])) in ids_equipos]

    guardar("male_teams_fc24_top5.csv", col_equipos, equipos)
    guardar("male_players_fc24_top5.csv", col_jugadores, jugadores)

    if (ORIGEN / "male_coaches.csv").exists():
        ids_entrenadores = {e["coach_id"] for e in equipos}
        col_ent, entrenadores = leer(ORIGEN / "male_coaches.csv")
        guardar("male_coaches_fc24_top5.csv", col_ent,
                [e for e in entrenadores if e["coach_id"] in ids_entrenadores])
    else:
        print("  (sin male_coaches.csv: se omite)")


def filtrar_transfermarkt():
    archivos = ("players.csv", "clubs.csv", "games.csv")
    if not all((ORIGEN_TM / a).exists() for a in archivos):
        print("Transfermarkt: no estan los tres archivos en datos_originales/transfermarkt/, se omite.")
        return

    print("Transfermarkt: leyendo jugadores, clubes y partidos...")
    _, jugadores = leer(ORIGEN_TM / "players.csv")
    jugadores = [j for j in jugadores
                 if (a_numero(j["last_season"]) or 0) >= TEMPORADA_MIN_JUGADORES_TM]
    guardar("tm_jugadores.csv", COLUMNAS_TM_JUGADORES, jugadores)

    _, clubes = leer(ORIGEN_TM / "clubs.csv")
    guardar("tm_clubes.csv", COLUMNAS_TM_CLUBES,
            [c for c in clubes if c["domestic_competition_id"] in LIGAS_TM])

    _, partidos = leer(ORIGEN_TM / "games.csv")
    guardar("tm_partidos_22_23.csv", COLUMNAS_TM_PARTIDOS,
            [p for p in partidos
             if p["competition_id"] in LIGAS_TM and a_numero(p["season"]) == TEMPORADA_TM])


def main():
    print("Archivos creados en datos_fuente/:")
    filtrar_ea()
    filtrar_transfermarkt()


if __name__ == "__main__":
    main()
