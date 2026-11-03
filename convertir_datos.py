"""Construye la base de datos de TransferAI combinando EA Sports FC 24 y Transfermarkt.

Entrada : datos_fuente/  (CSV ya filtrados por filtrar_originales.py, incluidos en el repositorio)
    male_players_fc24_top5.csv, male_teams_fc24_top5.csv, male_coaches_fc24_top5.csv  (EA Sports FC 24)
    tm_jugadores.csv, tm_clubes.csv, tm_partidos_22_23.csv                            (Transfermarkt)
Salida  : datos_reales/clubes.csv y datos_reales/jugadores.csv

Etapas:
    1. EA Sports FC 24: plantillas, ratings, salarios, contratos, atributos y táctica de cada club.
    2. Transfermarkt: valor de mercado real, agencia del jugador y datos del club (estadio, balance de traspasos).
    3. Temporada 2022/23: tabla de cada liga con los partidos disponibles.
    4. Cálculos propios: valor de referencia, competición europea 2023/24, presupuesto y perfil de mercado.

Uso: python convertir_datos.py
"""
import csv
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).parent
ORIGEN = RAIZ / "datos_fuente"
DESTINO = RAIZ / "datos_reales"

# ======================================================================
# PARÁMETROS DE DISEÑO (se pueden modificar)
# ======================================================================
ANIO_BASE = 2023                 # año de referencia para calcular años de contrato
SEMANAS_POR_ANIO = 52            # wage_eur de EA está expresado por semana
MIN_JUGADORES = 18               # los clubes con menos jugadores se descartan

# --- Presupuesto y tope salarial (no existen en los datos: son estimaciones de diseño)
FACTOR_PRESUPUESTO = 0.15        # presupuesto de fichajes = 15 % del valor total de la plantilla ...
BONUS_COMPETICION = {            # ... multiplicado por un bonus según la competición europea 2023/24
    "champions": 1.25,
    "europa_league": 1.10,
    "conference": 1.05,
    "no": 1.00,
}
FACTOR_TOPE_SALARIAL = 1.15      # tope salarial = masa salarial actual x este factor

# --- Valor de mercado
TEMPORADA_MIN_VALOR_TM = 2021    # se usa el valor de Transfermarkt solo si el jugador estaba activo desde esta temporada

# --- Perfil de mercado del club según su balance neto de traspasos en Transfermarkt (millones de euros)
UMBRAL_PERFIL_MERCADO = 10.0     # balance < -10 -> "comprador"; balance > +10 -> "vendedor"; resto -> "equilibrado"

# --- Competición europea real de la temporada 2023/24 (fase de grupos, fuente: UEFA / Wikipedia)
COMPETICION_2023_24 = {
    "champions": [
        "Manchester City", "Manchester United", "Arsenal", "Newcastle United",
        "Real Madrid", "FC Barcelona", "Atlético Madrid", "Real Sociedad", "Sevilla",
        "Inter", "Milan", "Napoli", "Lazio",
        "FC Bayern München", "Borussia Dortmund", "RB Leipzig", "FC Union Berlin",
        "Paris Saint Germain", "Lens",
    ],
    "europa_league": [
        "West Ham United", "Brighton & Hove Albion", "Liverpool",
        "Real Betis", "Villarreal", "Atalanta", "Roma",
        "SC Freiburg", "Bayer 04 Leverkusen",
        "Olympique de Marseille", "Toulouse", "Rennes",
    ],
    "conference": ["Aston Villa", "Fiorentina", "Eintracht Frankfurt", "Lille"],
}

#======================================================================
# CONVERSION DE DATOS (NO se pueden modificar)
# ======================================================================

# --- Equivalencia de clubes EA -> Transfermarkt (club_id). None = el club no tiene datos en Transfermarkt.
EA_A_TRANSFERMARKT = {
    "AFC Bournemouth": 989, "Almería": 3302, "Arsenal": 11, "Aston Villa": 405, "Atalanta": 800,
    "Athletic Club": 621, "Atlético Madrid": 13, "Bayer 04 Leverkusen": 15, "Bologna": 1025,
    "Borussia Dortmund": 16, "Borussia Mönchengladbach": 18, "Brentford": 1148, "Brest": 3911,
    "Brighton & Hove Albion": 1237, "Burnley": 1132, "Cagliari": 1390, "Celta de Vigo": 940,
    "Chelsea": 631, "Clermont": 3524, "Crystal Palace": 873, "Cádiz": 2687, "Darmstadt 98": 105,
    "Deportivo Alavés": 1108, "Eintracht Frankfurt": 24, "Empoli": 749, "Everton": 29,
    "FC Augsburg": 167, "FC Barcelona": 131, "FC Bayern München": 27, "FC Köln": 3,
    "FC Union Berlin": 89, "FSV Mainz 05": 39, "Fiorentina": 430, "Frosinone": 8970, "Fulham": 931,
    "Genoa": 252, "Getafe": 3709, "Girona": 12321, "Granada": 16795, "Heidenheim": None,
    "Hellas Verona": 276, "Inter": 46, "Juventus": 506, "Las Palmas": 472, "Lazio": 398,
    "Le Havre": None, "Lecce": 1005, "Lens": 826, "Lille": 1082, "Liverpool": 31, "Lorient": 1158,
    "Luton Town": None, "Mallorca": 237, "Manchester City": 281, "Manchester United": 985,
    "Metz": 347, "Milan": 5, "Monaco": 162, "Montpellier": 969, "Monza": 2919, "Nantes": 995,
    "Napoli": 6195, "Newcastle United": 762, "Nice": 417, "Nottingham Forest": 703,
    "Olympique Lyonnais": 1041, "Olympique de Marseille": 244, "Osasuna": 331,
    "Paris Saint Germain": 583, "RB Leipzig": 23826, "Rayo Vallecano": 367, "Real Betis": 150,
    "Real Madrid": 418, "Real Sociedad": 681, "Rennes": 273, "Roma": 12, "SC Freiburg": 60,
    "Salernitana": 380, "Sassuolo": 6574, "Sevilla": 368, "Sheffield United": 350,
    "Stade de Reims": 1421, "Strasbourg": 667, "TSG Hoffenheim": 533, "Torino": 416,
    "Tottenham Hotspur": 148, "Toulouse": 415, "Udinese": 410, "Valencia": 1049,
    "VfB Stuttgart": 79, "VfL Bochum 1848": 80, "VfL Wolfsburg": 82, "Villarreal": 1050,
    "Werder Bremen": 86, "West Ham United": 379, "Wolverhampton Wanderers": 543,
}

LIGAS_ID = {13, 53, 31, 19, 16}  # Premier League, LaLiga, Serie A, Bundesliga, Ligue 1

POSICIONES = {
    "GK": "POR",
    "CB": "DFC",
    "LB": "LAT", "RB": "LAT", "LWB": "LAT", "RWB": "LAT",
    "CDM": "MED", "CM": "MED", "CAM": "MED",
    "LM": "EXT", "RM": "EXT", "LW": "EXT", "RW": "EXT",
    "ST": "DEL", "CF": "DEL",
}

# Traducción de los estilos tácticos de EA
ESTILO_DEFENSIVO = {"Balanced": "equilibrado", "Press after possession loss": "presión tras pérdida",
                    "Pressure on heavy touch": "presión al mal control"}
CONSTRUCCION = {"Slow build up": "construcción lenta", "Balanced": "equilibrada",
                "Fast build up": "construcción rápida", "Long ball": "balón largo"}
CREACION = {"Possession": "posesión", "Balanced": "equilibrada",
            "Forward runs": "desmarques en profundidad", "Direct passing": "pase directo"}

csv.field_size_limit(10_000_000)


# ======================================================================
# UTILIDADES
# ======================================================================
def a_numero(texto):
    try:
        valor = float(texto)
    except (TypeError, ValueError):
        return None
    return None if valor != valor else valor  # descarta "nan"


def leer(nombre, obligatorio=True):
    archivo = ORIGEN / nombre
    if not archivo.exists():
        if obligatorio:
            sys.exit(f"Falta datos_fuente/{nombre}. Ejecuta antes filtrar_originales.py.")
        return []
    with open(archivo, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def palabras(texto):
    """'Vinícius Júnior' -> {'vinicius', 'junior'} (sin tildes ni mayúsculas)."""
    sin_tildes = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return set(re.sub(r"[^a-z ]", " ", sin_tildes.lower()).split())


def millones(valor):
    return round(valor / 1e6, 2) if valor else 0


def traducir_pie(texto):
    return {"left": "izquierdo", "right": "derecho"}.get((texto or "").strip().lower(), "")


def balance_traspasos(texto):
    """'€-33.80m' -> -33.8 ; '+€5.43m' -> 5.43 ; '€-450k' -> -0.45 ; '+-0' -> 0 (millones de euros)."""
    if not texto:
        return None
    t = texto.replace("€", "").replace("+", "").strip()
    if t in ("-0", "0", ""):
        return 0.0
    factor = 1.0 if t.endswith("m") else 0.001 if t.endswith("k") else 1e-6
    try:
        return round(float(t.rstrip("mk")) * factor, 2)
    except ValueError:
        return None


# ======================================================================
# 1. EA SPORTS FC 24
# ======================================================================
def inferir_formacion(posiciones_once):
    """Deduce la formación a partir de las posiciones del once titular en EA (por ejemplo LCB, RDM, ST)."""
    c = Counter(posiciones_once)
    centrales = c["CB"] + c["LCB"] + c["RCB"]
    laterales = c["LB"] + c["RB"]
    carrileros = c["LWB"] + c["RWB"]
    pivotes = c["CDM"] + c["LDM"] + c["RDM"]
    interiores = c["CM"] + c["LCM"] + c["RCM"]
    volantes = c["LM"] + c["RM"]
    enganches = c["CAM"] + c["LAM"] + c["RAM"]
    extremos = c["LW"] + c["RW"]
    segundas_puntas = c["LF"] + c["RF"]
    delanteros = c["ST"] + c["LS"] + c["RS"] + c["CF"]

    if centrales == 3:  # línea de tres
        medios = carrileros + volantes + pivotes + interiores
        if segundas_puntas == 2 and delanteros == 1:
            return f"3-{medios}-2-1"
        return f"3-{medios}-{enganches + extremos + segundas_puntas + delanteros}"
    defensa = centrales + laterales
    if extremos == 2:
        return f"{defensa}-{pivotes + interiores + enganches}-3"
    if pivotes == 2 and enganches == 1 and volantes == 2:
        return f"{defensa}-2-3-1"
    if pivotes == 2 and c["LAM"] + c["RAM"] == 2:
        return f"{defensa}-2-2-2"
    if delanteros == 2:
        if pivotes == 1 and enganches == 1:
            return f"{defensa}-1-2-1-2"
        return f"{defensa}-4-2"
    if pivotes == 1 and interiores == 2 and volantes == 2:
        return f"{defensa}-1-4-1"
    if enganches == 1 and interiores == 2 and volantes == 2:
        return f"{defensa}-4-1-1"
    if segundas_puntas == 2:
        return f"{defensa}-3-2-1"
    return f"{defensa}-{pivotes + interiores + volantes + enganches}-{extremos + segundas_puntas + delanteros}"


def cargar_equipos_ea():
    entrenadores = {e["coach_id"]: e["long_name"] for e in leer("male_coaches_fc24_top5.csv", False)}
    filas = [f for f in leer("male_teams_fc24_top5.csv")
             if a_numero(f["league_id"]) in LIGAS_ID and a_numero(f["league_level"]) == 1]
    nombres = {int(a_numero(f["team_id"])): f["team_name"] for f in filas}

    equipos = {}
    for f in filas:
        rival = a_numero(f["rival_team"])
        equipos[int(a_numero(f["team_id"]))] = {
            "nombre": f["team_name"],
            "liga": f["league_name"],
            "overall": a_numero(f["overall"]) or 0,
            "prestigio": a_numero(f["international_prestige"]) or 1,
            "rival": nombres.get(int(rival), f["rival_team"]) if rival is not None else "",
            "ataque": int(a_numero(f["attack"]) or 0),
            "mediocampo": int(a_numero(f["midfield"]) or 0),
            "defensa": int(a_numero(f["defence"]) or 0),
            "prestigio_domestico": int(a_numero(f["domestic_prestige"]) or 0),
            "entrenador": entrenadores.get(f["coach_id"], ""),
            "capitan_id": int(a_numero(f["captain"]) or 0),
            "estilo_defensivo": ESTILO_DEFENSIVO.get(f["def_style"], f["def_style"]),
            "construccion": CONSTRUCCION.get(f["off_build_up_play"], f["off_build_up_play"]),
            "creacion_ocasiones": CREACION.get(f["off_chance_creation"], f["off_chance_creation"]),
            "anchura_ofensiva": int(a_numero(f["off_team_width"]) or 0),
            "profundidad_defensiva": int(a_numero(f["def_team_depth"]) or 0),
            "jugadores_en_area": int(a_numero(f["off_players_in_box"]) or 0),
        }
    return equipos


def atributos_ea(f):
    """Atributos de juego de EA (0 a 99). Los porteros no tienen los seis atributos de campo."""
    def num(columna):
        v = a_numero(f[columna])
        return int(v) if v is not None else ""
    porteria = [a_numero(f[c]) for c in ("goalkeeping_diving", "goalkeeping_handling",
                                          "goalkeeping_positioning", "goalkeeping_reflexes")]
    es_portero = (f["player_positions"] or "").startswith("GK")
    return {
        "at_ritmo": num("pace"), "at_tiro": num("shooting"), "at_pase": num("passing"),
        "at_regate": num("dribbling"), "at_defensa": num("defending"), "at_fisico": num("physic"),
        "at_cabezazo": num("attacking_heading_accuracy"), "at_vision": num("mentality_vision"),
        "at_resistencia": num("power_stamina"),
        "at_porteria": round(sum(porteria) / 4) if es_portero and None not in porteria else "",
    }


# ======================================================================
# 2. TRANSFERMARKT
# ======================================================================
def indexar_transfermarkt():
    """Agrupa los jugadores de Transfermarkt por fecha de nacimiento para cruzarlos con EA."""
    por_fecha = defaultdict(list)
    for t in leer("tm_jugadores.csv", False):
        fecha = (t["date_of_birth"] or "")[:10]
        if fecha:
            por_fecha[fecha].append(t)
    return por_fecha


def cruzar_jugador(fila_ea, por_fecha, usados):
    """Busca al jugador en Transfermarkt: misma fecha de nacimiento y al menos una palabra del nombre en común."""
    candidatos = por_fecha.get((fila_ea["dob"] or "")[:10], [])
    nombre_ea = palabras(fila_ea["long_name"]) | palabras(fila_ea["short_name"])
    mejor, coincidencias = None, 0
    for t in candidatos:
        n = len(nombre_ea & palabras(t["name"]))
        if n > coincidencias and t["player_id"] not in usados:
            mejor, coincidencias = t, n
    return mejor


# ======================================================================
# 3. TEMPORADA 2022/23
# ======================================================================
def tabla_22_23():
    """Tabla de cada liga con los partidos disponibles (el dataset llega hasta la fecha 28 a 31)."""
    puntos = defaultdict(lambda: {"liga": "", "pj": 0, "pts": 0, "gf": 0, "gc": 0})
    for p in leer("tm_partidos_22_23.csv", False):
        gl, gv = a_numero(p["home_club_goals"]), a_numero(p["away_club_goals"])
        if gl is None or gv is None:
            continue
        for club, a_favor, en_contra in ((p["home_club_id"], gl, gv), (p["away_club_id"], gv, gl)):
            fila = puntos[int(club)]
            fila["liga"] = p["competition_id"]
            fila["pj"] += 1
            fila["gf"] += a_favor
            fila["gc"] += en_contra
            fila["pts"] += 3 if a_favor > en_contra else 1 if a_favor == en_contra else 0

    tabla = {}
    por_liga = defaultdict(list)
    for club, fila in puntos.items():
        por_liga[fila["liga"]].append((club, fila))
    for lista in por_liga.values():
        lista.sort(key=lambda x: (x[1]["pts"], x[1]["gf"] - x[1]["gc"], x[1]["gf"]), reverse=True)
        for posicion, (club, fila) in enumerate(lista, start=1):
            tabla[club] = {"posicion": posicion, "ppp": round(fila["pts"] / fila["pj"], 2)}
    return tabla


# ======================================================================
# PROGRAMA PRINCIPAL
# ======================================================================
def main():
    equipos = cargar_equipos_ea()
    if not equipos:
        sys.exit("No se encontró ningún club de las cinco ligas en male_teams_fc24_top5.csv.")
    clubes_tm = {int(c["club_id"]): c for c in leer("tm_clubes.csv", False)}
    tabla = tabla_22_23()
    por_fecha = indexar_transfermarkt()
    competicion = {club: comp for comp, lista in COMPETICION_2023_24.items() for club in lista}

    # ------------------------------------------------ jugadores
    descartes = defaultdict(int)
    por_club = defaultdict(list)
    posiciones_once = defaultdict(list)
    usados_tm = set()

    for f in leer("male_players_fc24_top5.csv"):
        team_id = a_numero(f["club_team_id"])
        if team_id is None or int(team_id) not in equipos:
            continue
        team_id = int(team_id)
        en_once = (f["club_position"] or "").strip().upper()
        if en_once not in ("", "SUB", "RES", "GK"):
            posiciones_once[team_id].append(en_once)

        posicion_ea = (f["player_positions"] or "").split(",")[0].strip().upper()
        pos = POSICIONES.get(posicion_ea)
        valor_ea, sueldo = a_numero(f["value_eur"]), a_numero(f["wage_eur"])
        anio, edad, rating = a_numero(f["club_contract_valid_until_year"]), a_numero(f["age"]), a_numero(f["overall"])
        pid = a_numero(f["player_id"])
        if pos is None:
            descartes["posición desconocida"] += 1
            continue
        if None in (valor_ea, sueldo, anio, edad, rating, pid) or valor_ea <= 0 or sueldo <= 0:
            descartes["datos incompletos"] += 1
            continue

        # Cruce con Transfermarkt
        tm = cruzar_jugador(f, por_fecha, usados_tm)
        valor_tm = valor_max_tm = None
        agencia = ""
        if tm is not None:
            usados_tm.add(tm["player_id"])
            agencia = tm["agent_name"] if tm["agent_name"] not in ("", "null") else ""
            if (a_numero(tm["last_season"]) or 0) >= TEMPORADA_MIN_VALOR_TM:
                valor_tm = a_numero(tm["market_value_in_eur"])
                valor_max_tm = a_numero(tm["highest_market_value_in_eur"])

        # Valor de referencia: Transfermarkt (mercado real) si existe; si no, EA
        if valor_tm:
            valor_referencia, fuente_valor = valor_tm, "transfermarkt"
        else:
            valor_referencia, fuente_valor = valor_ea, "ea"

        potencial = a_numero(f["potential"])
        clausula = a_numero(f["release_clause_eur"])
        por_club[team_id].append({
            "id": int(pid),
            "nombre": f["short_name"],
            "edad": int(edad),
            "posicion": pos,
            "club": equipos[team_id]["nombre"],
            "nacionalidad": f["nationality_name"],
            "valor_mercado": millones(valor_referencia),
            "salario_anual": round(sueldo * SEMANAS_POR_ANIO / 1e6, 3),
            "anios_contrato": max(1, int(anio) - ANIO_BASE),
            "rating": int(rating),
            "titular": "no" if en_once in ("", "SUB", "RES") else "si",
            "potencial": max(int(rating), int(potencial if potencial is not None else rating)),
            "reputacion_internacional": int(a_numero(f["international_reputation"]) or 1),
            "clausula_rescision": millones(clausula) if clausula and clausula > 0 else 0,
            "pie": traducir_pie(f["preferred_foot"]),
            # --- nuevos (Hito 3)
            "valor_ea": millones(valor_ea),
            "valor_tm": millones(valor_tm) if valor_tm else "",
            "valor_max_tm": millones(valor_max_tm) if valor_max_tm else "",
            "fuente_valor": fuente_valor,
            "agencia": agencia,
            "altura": int(a_numero(f["height_cm"]) or 0),
            "posicion_ea": posicion_ea,
            "posiciones_alternativas": ",".join(p.strip() for p in (f["player_positions"] or "").split(",")[1:]),
            "posicion_en_once": en_once if en_once not in ("SUB", "RES") else "",
            "capitan": "si" if int(pid) == equipos[team_id]["capitan_id"] else "no",
            "cedido_por": f["club_loaned_from"] or "",   # club dueño del jugador si está a préstamo
            "ritmo_trabajo": f["work_rate"],
            **atributos_ea(f),
        })

    # ------------------------------------------------ clubes
    clubes, jugadores = [], []
    for team_id, plantilla in por_club.items():
        eq = equipos[team_id]
        if len(plantilla) < MIN_JUGADORES:
            descartes["clubes con pocos jugadores"] += 1
            continue
        tm_id = EA_A_TRANSFERMARKT.get(eq["nombre"])
        tm_club = clubes_tm.get(tm_id, {}) if tm_id else {}
        balance = balance_traspasos(tm_club.get("net_transfer_record"))
        if (a_numero(tm_club.get("last_season")) or 0) < 2022:
            balance = None  # el dato de Transfermarkt es de una temporada antigua: no se usa
        if balance is None:
            perfil = "desconocido"
        elif balance < -UMBRAL_PERFIL_MERCADO:
            perfil = "comprador"
        elif balance > UMBRAL_PERFIL_MERCADO:
            perfil = "vendedor"
        else:
            perfil = "equilibrado"

        comp = competicion.get(eq["nombre"], "no")
        en_tabla = tabla.get(tm_id) if tm_id else None
        masa = sum(j["salario_anual"] for j in plantilla)
        valor_plantilla = sum(j["valor_mercado"] for j in plantilla)
        capitan = next((j["nombre"] for j in plantilla if j["capitan"] == "si"), "")

        clubes.append({
            "club": eq["nombre"],
            "liga": eq["liga"],
            "nivel": max(1, min(10, int(eq["prestigio"]))),
            "presupuesto_fichajes": round(valor_plantilla * FACTOR_PRESUPUESTO * BONUS_COMPETICION[comp], 1),
            "tope_salarial": round(masa * FACTOR_TOPE_SALARIAL, 1),
            "competicion_internacional": comp,
            "rival": eq["rival"],
            "team_id": team_id,
            "rating_club": int(eq["overall"]),
            "ataque": eq["ataque"],
            "mediocampo": eq["mediocampo"],
            "defensa": eq["defensa"],
            "prestigio_domestico": eq["prestigio_domestico"],
            "edad_media": round(sum(j["edad"] for j in plantilla) / len(plantilla), 1),
            "valor_plantilla": round(valor_plantilla, 1),
            # --- nuevos (Hito 3)
            "entrenador": eq["entrenador"],
            "capitan": capitan,
            "formacion": inferir_formacion(posiciones_once[team_id]),
            "estilo_defensivo": eq["estilo_defensivo"],
            "construccion": eq["construccion"],
            "creacion_ocasiones": eq["creacion_ocasiones"],
            "anchura_ofensiva": eq["anchura_ofensiva"],
            "profundidad_defensiva": eq["profundidad_defensiva"],
            "jugadores_en_area": eq["jugadores_en_area"],
            "posicion_22_23": en_tabla["posicion"] if en_tabla else "",
            "puntos_por_partido_22_23": en_tabla["ppp"] if en_tabla else "",
            "ascendido": "no" if en_tabla else "si",
            "aforo_estadio": int(a_numero(tm_club.get("stadium_seats")) or 0) or "",
            "balance_traspasos": balance if balance is not None else "",
            "perfil_mercado": perfil,
            "_masa": round(masa, 1),
            "_n": len(plantilla),
        })
        jugadores.extend(plantilla)

    por_liga = defaultdict(list)
    for c in clubes:
        por_liga[c["liga"]].append(c)
    for lista in por_liga.values():
        for c in lista:
            c["n_clubes_liga"] = len(lista)
        # ranking por línea dentro de la liga (1 = la mejor; empates comparten puesto)
        for linea in ("ataque", "mediocampo", "defensa"):
            for c in lista:
                c[f"rank_{linea}"] = 1 + sum(1 for o in lista if o[linea] > c[linea])

    clubes.sort(key=lambda c: c["club"])
    jugadores.sort(key=lambda j: j["id"])

    # ------------------------------------------------ escritura
    DESTINO.mkdir(exist_ok=True)
    campos_clubes = ["club", "liga", "nivel", "presupuesto_fichajes", "tope_salarial",
                     "competicion_internacional", "rival", "team_id", "rating_club", "ataque",
                     "mediocampo", "defensa", "prestigio_domestico", "rank_ataque",
                     "rank_mediocampo", "rank_defensa", "n_clubes_liga", "edad_media",
                     "valor_plantilla", "entrenador", "capitan", "formacion", "estilo_defensivo",
                     "construccion", "creacion_ocasiones", "anchura_ofensiva", "profundidad_defensiva",
                     "jugadores_en_area", "posicion_22_23", "puntos_por_partido_22_23", "ascendido",
                     "aforo_estadio", "balance_traspasos", "perfil_mercado"]
    with open(DESTINO / "clubes.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos_clubes, extrasaction="ignore")
        w.writeheader()
        w.writerows(clubes)

    campos_jug = ["id", "nombre", "edad", "posicion", "club", "nacionalidad", "valor_mercado",
                  "salario_anual", "anios_contrato", "rating", "titular", "potencial",
                  "reputacion_internacional", "clausula_rescision", "pie",
                  "valor_ea", "valor_tm", "valor_max_tm", "fuente_valor", "agencia", "altura",
                  "posicion_ea", "posiciones_alternativas", "posicion_en_once", "capitan", "cedido_por", "ritmo_trabajo",
                  "at_ritmo", "at_tiro", "at_pase", "at_regate", "at_defensa", "at_fisico",
                  "at_cabezazo", "at_vision", "at_resistencia", "at_porteria"]
    with open(DESTINO / "jugadores.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos_jug)
        w.writeheader()
        w.writerows(jugadores)

    informe(clubes, jugadores, descartes)


# ======================================================================
# INFORME DE VERIFICACIÓN
# ======================================================================
def informe(clubes, jugadores, descartes):
    n = len(jugadores)
    con_tm = sum(1 for j in jugadores if j["fuente_valor"] == "transfermarkt")
    print("=== INFORME DE CONVERSIÓN ===")
    print(f"Clubes: {len(clubes)} | Jugadores: {n}")
    print("Descartes:", dict(descartes) or "ninguno")

    print("\n--- Cruce con Transfermarkt ---")
    print(f"Jugadores con valor de Transfermarkt: {con_tm} de {n} ({100 * con_tm / n:.0f} %); el resto usa el valor de EA")
    print(f"Jugadores cedidos (no se pueden comprar a su club actual): {sum(1 for j in jugadores if j['cedido_por'])}")
    print(f"Jugadores con agencia conocida: {sum(1 for j in jugadores if j['agencia'])} de {n}")
    agencias = Counter(j["agencia"] for j in jugadores if j["agencia"])
    print("Agencias con más jugadores:", ", ".join(f"{a} ({k})" for a, k in agencias.most_common(6)))
    pares = [(j["valor_tm"], j["valor_ea"]) for j in jugadores if j["valor_tm"]]
    print(f"Valor total EA {sum(e for _, e in pares):,.0f} M€ vs Transfermarkt {sum(t for t, _ in pares):,.0f} M€ "
          "(jugadores cruzados)")

    print("\n--- Clubes ---")
    print("Competición 2023/24:", dict(Counter(c["competicion_internacional"] for c in clubes)))
    print("Perfil de mercado:", dict(Counter(c["perfil_mercado"] for c in clubes)))
    print("Formaciones:", dict(Counter(c["formacion"] for c in clubes).most_common()))
    print("Ascendidos (sin datos 2022/23 en primera):", [c["club"] for c in clubes if c["ascendido"] == "si"])
    print("Clubes sin entrenador:", [c["club"] for c in clubes if not c["entrenador"]] or "ninguno")
    no_encontrados = set(sum(COMPETICION_2023_24.values(), [])) - {c["club"] for c in clubes}
    print("Clubes de COMPETICION_2023_24 que no existen en los datos:", no_encontrados or "ninguno")

    print("\nTop 10 clubes por presupuesto (millones de euros):")
    for c in sorted(clubes, key=lambda c: c["presupuesto_fichajes"], reverse=True)[:10]:
        print(f"  {c['club']:<24} pres={c['presupuesto_fichajes']:>6} tope={c['tope_salarial']:>6} "
              f"comp={c['competicion_internacional']:<13} perfil={c['perfil_mercado']}")

    print("\nClubes de control:")
    for nombre in ("Fiorentina", "Newcastle United", "FC Barcelona", "Valencia"):
        c = next((c for c in clubes if c["club"] == nombre), None)
        if c:
            print(f"  {c['club']}: {c['formacion']}, {c['estilo_defensivo']}, {c['construccion']}, "
                  f"{c['creacion_ocasiones']} | entrenador {c['entrenador']} | capitán {c['capitan']} | "
                  f"2022/23: {c['posicion_22_23']}° ({c['puntos_por_partido_22_23']} pts/partido) | "
                  f"pres={c['presupuesto_fichajes']} | estadio {c['aforo_estadio']}")


if __name__ == "__main__":
    main()
