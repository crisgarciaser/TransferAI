"""Convierte los CSV de EA Sports FC 24 al formato que usa TransferAI.

Entrada : datos_originales/male_players.csv y male_teams.csv
Salida  : datos_reales/clubes.csv y datos_reales/jugadores.csv
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).parent
ORIGEN = RAIZ / "datos_originales"
DESTINO = RAIZ / "datos_reales"

# ------------------------------------------------------------------
# Parámetros de diseño (se pueden modificar)
# ------------------------------------------------------------------
VERSION = 24
LIGAS_ID = {13, 53, 31, 19, 16}  # Premier League, LaLiga, Serie A, Bundesliga, Ligue 1
ANIO_BASE = 2023                 # año de referencia para calcular años de contrato
SEMANAS_POR_ANIO = 52            # wage_eur está expresado por semana
FACTOR_TOPE_SALARIAL = 1.15      # tope salarial = masa salarial actual x este factor
FACTOR_PRESUPUESTO = 0.15        # presupuesto de fichajes = % del valor total de la plantilla (si el dataset no lo trae)
TOP_INTERNACIONAL = 6            # los N mejores clubes de cada liga "juegan" competición internacional
MIN_JUGADORES = 18               # los clubes con menos jugadores se descartan

POSICIONES = {
    "GK": "POR",
    "CB": "DFC",
    "LB": "LAT", "RB": "LAT", "LWB": "LAT", "RWB": "LAT",
    "CDM": "MED", "CM": "MED", "CAM": "MED",
    "LM": "EXT", "RM": "EXT", "LW": "EXT", "RW": "EXT",
    "ST": "DEL", "CF": "DEL",
}


def a_numero(texto):
    try:
        valor = float(texto)
    except (TypeError, ValueError):
        return None
    return None if valor != valor else valor  # descarta "nan"


def leer_filas(archivo):
    with open(archivo, encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def cargar_equipos():
    filas = [f for f in leer_filas(ORIGEN / "male_teams.csv")
             if a_numero(f["fifa_version"]) == VERSION]
    if not filas:
        sys.exit(f"No hay filas de equipos para la versión {VERSION}.")
    ultima = max(a_numero(f["fifa_update"]) or 0 for f in filas)
    filas = [f for f in filas if (a_numero(f["fifa_update"]) or 0) == ultima]

    equipos, ligas_vistas = {}, {}
    for f in filas:
        liga_id = a_numero(f["league_id"])
        if a_numero(f["league_level"]) != 1 or liga_id is None:
            continue
        ligas_vistas[int(liga_id)] = f["league_name"]
        if int(liga_id) not in LIGAS_ID:
            continue
        team_id = a_numero(f["team_id"])
        if team_id is None:
            continue
        equipos[int(team_id)] = {
            "nombre": f["team_name"],
            "liga": f["league_name"],
            "overall": a_numero(f["overall"]) or 0,
            "prestigio": a_numero(f["international_prestige"]) or 1,
            "presupuesto": (a_numero(f["transfer_budget_eur"]) or 0) / 1e6,
            "rival": f["rival_team"],
            "team_id": int(team_id),
        }
    return equipos, ultima, ligas_vistas


def cargar_jugadores():
    filas, ultima = [], 0
    for f in leer_filas(ORIGEN / "male_players.csv"):
        if a_numero(f["fifa_version"]) != VERSION:
            continue
        upd = a_numero(f["fifa_update"]) or 0
        ultima = max(ultima, upd)
        filas.append({
            "player_id": f["player_id"],
            "short_name": f["short_name"],
            "player_positions": f["player_positions"],
            "overall": f["overall"],
            "value_eur": f["value_eur"],
            "wage_eur": f["wage_eur"],
            "age": f["age"],
            "club_team_id": f["club_team_id"],
            "club_position": f["club_position"],
            "anio_contrato": f["club_contract_valid_until_year"],
            "nacionalidad": f["nationality_name"],
            "upd": upd,
        })
    return [r for r in filas if r["upd"] == ultima], ultima


def main():
    equipos, upd_equipos, ligas_vistas = cargar_equipos()
    if not equipos:
        print("No se encontró ningún club con LIGAS_ID. Ligas de primer nivel disponibles:")
        for lid, nombre in sorted(ligas_vistas.items()):
            print(f"  {lid}: {nombre}")
        sys.exit("Ajusta LIGAS_ID al inicio del script.")

    filas, upd_jugadores = cargar_jugadores()

    descartes = defaultdict(int)
    por_club = defaultdict(list)
    for r in filas:
        team_id = a_numero(r["club_team_id"])
        if team_id is None or int(team_id) not in equipos:
            continue
        primera = (r["player_positions"] or "").split(",")[0].strip().upper()
        pos = POSICIONES.get(primera)
        if pos is None:
            descartes["posición desconocida"] += 1
            continue
        valor = a_numero(r["value_eur"])
        sueldo = a_numero(r["wage_eur"])
        anio = a_numero(r["anio_contrato"])
        edad = a_numero(r["age"])
        rating = a_numero(r["overall"])
        pid = a_numero(r["player_id"])
        if None in (valor, sueldo, anio, edad, rating, pid) or valor <= 0 or sueldo <= 0:
            descartes["datos incompletos"] += 1
            continue
        titular = "no" if (r["club_position"] or "").strip().upper() in ("", "SUB", "RES") else "si"
        por_club[int(team_id)].append({
            "id": int(pid),
            "nombre": r["short_name"],
            "edad": int(edad),
            "posicion": pos,
            "club": equipos[int(team_id)]["nombre"],
            "nacionalidad": r["nacionalidad"],
            "valor_mercado": round(valor / 1e6, 2),
            "salario_anual": round(sueldo * SEMANAS_POR_ANIO / 1e6, 3),
            "anios_contrato": max(1, int(anio) - ANIO_BASE),
            "rating": int(rating),
            "titular": titular,
        })

    clubes, jugadores = [], []
    for team_id, plantilla in por_club.items():
        if len(plantilla) < MIN_JUGADORES:
            descartes["clubes con pocos jugadores"] += 1
            continue
        eq = equipos[team_id]
        masa = sum(j["salario_anual"] for j in plantilla)
        valor_plantilla = sum(j["valor_mercado"] for j in plantilla)
        clubes.append({
            "club": eq["nombre"],
            "liga": eq["liga"],
            "nivel": max(1, min(10, int(eq["prestigio"]))),
            "presupuesto_fichajes": round(eq["presupuesto"] if eq["presupuesto"] > 0
                                          else valor_plantilla * FACTOR_PRESUPUESTO, 1),
            "tope_salarial": round(masa * FACTOR_TOPE_SALARIAL, 1),
            "competicion_internacional": "no",
            "rival": eq["rival"],
            "team_id": eq["team_id"],
            "_overall": eq["overall"],
            "_masa": round(masa, 1),
            "_n": len(plantilla),
        })
        jugadores.extend(plantilla)

    por_liga = defaultdict(list)
    for c in clubes:
        por_liga[c["liga"]].append(c)
    for lista in por_liga.values():
        lista.sort(key=lambda c: c["_overall"], reverse=True)
        for i, c in enumerate(lista):
            c["competicion_internacional"] = "si" if i < TOP_INTERNACIONAL else "no"

    clubes.sort(key=lambda c: c["club"])
    jugadores.sort(key=lambda j: j["id"])

    DESTINO.mkdir(exist_ok=True)
    campos_clubes = ["club", "liga", "nivel", "presupuesto_fichajes", "tope_salarial",
                     "competicion_internacional", "rival", "team_id"]
    with open(DESTINO / "clubes.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos_clubes, extrasaction="ignore")
        w.writeheader()
        w.writerows(clubes)

    campos_jug = ["id", "nombre", "edad", "posicion", "club", "nacionalidad", "valor_mercado",
                  "salario_anual", "anios_contrato", "rating", "titular"]
    with open(DESTINO / "jugadores.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos_jug)
        w.writeheader()
        w.writerows(jugadores)

    # ----------------------------- informe de verificación
    print("=== INFORME DE CONVERSIÓN ===")
    print(f"Versión {VERSION} | actualización equipos: {upd_equipos:g} | jugadores: {upd_jugadores:g}")
    print("Ligas incluidas:", sorted({c["liga"] for c in clubes}))
    print(f"Clubes: {len(clubes)} | Jugadores: {len(jugadores)}")
    print("Descartes:", dict(descartes) or "ninguno")
    print("Clubes sin presupuesto de fichajes:", sum(1 for c in clubes if c["presupuesto_fichajes"] == 0))
    print("\nTop 10 clubes por presupuesto (millones de euros):")
    for c in sorted(clubes, key=lambda c: c["presupuesto_fichajes"], reverse=True)[:10]:
        print(f"  {c['club']:<26} {c['liga'][:16]:<16} pres={c['presupuesto_fichajes']:>6} "
              f"masa={c['_masa']:>6} tope={c['tope_salarial']:>6} nivel={c['nivel']} jug={c['_n']}")
    print("\nMuestra de jugadores:")
    for j in jugadores[:5]:
        print("  ", j)


if __name__ == "__main__":
    main()