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

    # nombres de todos los equipos de esta versión/actualización (para resolver "rival")
    nombres = {}
    for f in filas:
        tid = a_numero(f["team_id"])
        if tid is not None:
            nombres[int(tid)] = f["team_name"]

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
            "rival": resolver_rival(f["rival_team"], nombres),
            "team_id": int(team_id),
            "ataque": int(a_numero(f["attack"]) or 0),
            "mediocampo": int(a_numero(f["midfield"]) or 0),
            "defensa": int(a_numero(f["defence"]) or 0),
            "prestigio_domestico": int(a_numero(f["domestic_prestige"]) or 0),
        }
    return equipos, ultima, ligas_vistas


def resolver_rival(valor, nombres):
    """Convierte el team_id del rival en su nombre; si no se puede, deja el valor original."""
    tid = a_numero(valor)
    if tid is not None and int(tid) in nombres:
        return nombres[int(tid)]
    return valor


def traducir_pie(texto):
    return {"left": "izquierdo", "right": "derecho"}.get((texto or "").strip().lower(), "")


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
            "potential": f["potential"],
            "international_reputation": f["international_reputation"],
            "release_clause_eur": f["release_clause_eur"],
            "preferred_foot": f["preferred_foot"],
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
        potencial = a_numero(r["potential"])
        clausula = a_numero(r["release_clause_eur"])
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
            "potencial": max(int(rating), int(potencial if potencial is not None else rating)),
            "reputacion_internacional": int(a_numero(r["international_reputation"]) or 1),
            "clausula_rescision": round(clausula / 1e6, 2) if clausula and clausula > 0 else 0,
            "pie": traducir_pie(r["preferred_foot"]),
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
            "rating_club": int(eq["overall"]),
            "ataque": eq["ataque"],
            "mediocampo": eq["mediocampo"],
            "defensa": eq["defensa"],
            "prestigio_domestico": eq["prestigio_domestico"],
            "edad_media": round(sum(j["edad"] for j in plantilla) / len(plantilla), 1),
            "valor_plantilla": round(valor_plantilla, 1),
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
            c["n_clubes_liga"] = len(lista)
        # ranking por línea dentro de la liga (1 = la mejor; empates comparten puesto)
        for linea in ("ataque", "mediocampo", "defensa"):
            for c in lista:
                c[f"rank_{linea}"] = 1 + sum(1 for o in lista if o[linea] > c[linea])

    clubes.sort(key=lambda c: c["club"])
    jugadores.sort(key=lambda j: j["id"])

    DESTINO.mkdir(exist_ok=True)
    campos_clubes = ["club", "liga", "nivel", "presupuesto_fichajes", "tope_salarial",
                     "competicion_internacional", "rival", "team_id", "rating_club", "ataque",
                     "mediocampo", "defensa", "prestigio_domestico", "rank_ataque",
                     "rank_mediocampo", "rank_defensa", "n_clubes_liga", "edad_media",
                     "valor_plantilla"]
    with open(DESTINO / "clubes.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos_clubes, extrasaction="ignore")
        w.writeheader()
        w.writerows(clubes)

    campos_jug = ["id", "nombre", "edad", "posicion", "club", "nacionalidad", "valor_mercado",
                  "salario_anual", "anios_contrato", "rating", "titular", "potencial",
                  "reputacion_internacional", "clausula_rescision", "pie"]
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

    print("\n--- Datos ampliados ---")
    en_cero = [c["club"] for c in clubes if 0 in (c["ataque"], c["mediocampo"], c["defensa"])]
    print("Clubes con alguna línea (ataque/medio/defensa) en cero:", en_cero or "ninguno")
    sin_resolver = [c["club"] for c in clubes if a_numero(c["rival"]) is not None or not c["rival"]]
    print("Clubes con rival sin resolver a nombre:", sin_resolver or "ninguno")
    print(f"Jugadores con potencial > rating: {sum(1 for j in jugadores if j['potencial'] > j['rating'])}"
          f" de {len(jugadores)}")
    print(f"Jugadores con cláusula de rescisión > 0: "
          f"{sum(1 for j in jugadores if j['clausula_rescision'] > 0)} de {len(jugadores)}")
    pies = defaultdict(int)
    for j in jugadores:
        pies[j["pie"] or "(vacío)"] += 1
    print("Distribución de pie hábil:", dict(pies))
    print("\nClubes de control:")
    for nombre in ("Fiorentina", "Newcastle United", "FC Barcelona"):
        c = next((c for c in clubes if c["club"] == nombre), None)
        if c is None:
            print(f"  {nombre}: no está en los datos")
            continue
        n = c["n_clubes_liga"]
        print(f"  {c['club']} ({c['liga']}) rival={c['rival']} | "
              f"ataque={c['ataque']} (#{c['rank_ataque']}/{n}) "
              f"medio={c['mediocampo']} (#{c['rank_mediocampo']}/{n}) "
              f"defensa={c['defensa']} (#{c['rank_defensa']}/{n}) | "
              f"pres={c['presupuesto_fichajes']} tope={c['tope_salarial']}")


if __name__ == "__main__":
    main()