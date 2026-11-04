"""Encaje táctico: qué tan bien calza un jugador con la forma de jugar de un club (Paso 16).

Tres piezas:
1. identidad_tactica(club): describe cómo juega el club (formación y estilo, datos de EA Sports FC 24).
2. perfil_tactico(jugador): qué tipo de jugador es según sus atributos (por ejemplo, "organizador").
3. encaje_tactico(jugador, club): puntaje 0-100 de los atributos que ese estilo necesita en esa posición,
   comparado con el titular actual del club, con los motivos principales.

Todas las ponderaciones están en las tablas de este archivo para poder ajustarlas fácilmente.
"""

ATRIBUTOS = {"ritmo": "at_ritmo", "tiro": "at_tiro", "pase": "at_pase", "regate": "at_regate",
             "defensa": "at_defensa", "fisico": "at_fisico", "cabezazo": "at_cabezazo", "vision": "at_vision",
             "resistencia": "at_resistencia", "porteria": "at_porteria"}

# ======================================================================
# PONDERACIONES
# ======================================================================
# Qué importa en cada posición, sin considerar el estilo del club
PESOS_BASE = {
    "POR": {"porteria": 1.0},
    "DFC": {"defensa": 0.40, "fisico": 0.25, "cabezazo": 0.20, "ritmo": 0.15},
    "LAT": {"ritmo": 0.30, "defensa": 0.30, "resistencia": 0.20, "pase": 0.20},
    "MED": {"pase": 0.30, "vision": 0.20, "defensa": 0.20, "resistencia": 0.15, "regate": 0.15},
    "EXT": {"ritmo": 0.30, "regate": 0.30, "tiro": 0.25, "pase": 0.15},
    "DEL": {"tiro": 0.40, "fisico": 0.15, "cabezazo": 0.15, "ritmo": 0.15, "regate": 0.15},
}

# Cuánto suma cada rasgo del estilo del club a cada atributo, por posición ("*" = todas las de campo)
AJUSTES_ESTILO = {
    ("construccion", "construcción lenta"): {"*": {"pase": 0.15, "vision": 0.10}},
    ("construccion", "construcción rápida"): {"*": {"ritmo": 0.15, "regate": 0.05}},
    ("construccion", "balón largo"): {"*": {"fisico": 0.10, "cabezazo": 0.10}},
    ("creacion_ocasiones", "posesión"): {"*": {"pase": 0.10, "vision": 0.05}},
    ("creacion_ocasiones", "desmarques en profundidad"): {"*": {"ritmo": 0.15}},
    ("creacion_ocasiones", "pase directo"): {"*": {"vision": 0.10, "fisico": 0.05}},
    ("estilo_defensivo", "presión tras pérdida"): {"*": {"resistencia": 0.15, "defensa": 0.05}},
    ("estilo_defensivo", "presión al mal control"): {"*": {"resistencia": 0.10, "defensa": 0.10}},
}
ANCHURA_ALTA = 65          # anchura_ofensiva >= esto: el club ataca abierto (laterales y extremos rápidos)
AJUSTE_ANCHURA = {"LAT": {"ritmo": 0.10, "regate": 0.05}, "EXT": {"ritmo": 0.10, "regate": 0.05}}
AREA_LLENA = 6             # jugadores_en_area >= esto: llega mucha gente al área (delantero de área)
AJUSTE_AREA = {"DEL": {"cabezazo": 0.10, "fisico": 0.05}, "EXT": {"tiro": 0.05}}
AJUSTES_FORMACION = {      # según cómo empieza o termina la formación
    "linea_de_3": {"LAT": {"resistencia": 0.10, "ritmo": 0.05}, "DFC": {"pase": 0.05}},   # carrileros
    "dos_delanteros": {"DEL": {"pase": 0.05, "regate": 0.05}},
    "tres_arriba": {"EXT": {"tiro": 0.05, "regate": 0.05}},
    "con_mediapunta": {"MED": {"vision": 0.10, "tiro": 0.05}},
}

NIVELES_ENCAJE = [(80, "alto"), (70, "medio"), (0, "bajo")]   # puntaje mínimo -> nivel


# ======================================================================
# IDENTIDAD DEL CLUB
# ======================================================================
def rasgos_formacion(formacion):
    rasgos = []
    partes = [int(x) for x in str(formacion).split("-") if x.isdigit()]
    if partes and partes[0] == 3:
        rasgos.append("linea_de_3")
    if partes and partes[-1] == 2:
        rasgos.append("dos_delanteros")
    if partes and partes[-1] == 3:
        rasgos.append("tres_arriba")
    if formacion in ("4-2-3-1", "4-4-1-1", "4-1-2-1-2", "3-4-2-1"):
        rasgos.append("con_mediapunta")
    return rasgos


def identidad_tactica(club):
    """Frase y datos de cómo juega un club (fila de clubes.csv)."""
    rasgos = []
    if club.get("anchura_ofensiva", 0) >= ANCHURA_ALTA:
        rasgos.append("ataca abierto")
    if club.get("jugadores_en_area", 0) >= AREA_LLENA:
        rasgos.append("llega con mucha gente al área")
    construccion = club["construccion"]
    if construccion == "equilibrada":
        construccion = "construcción equilibrada"
    creacion = club["creacion_ocasiones"]
    creacion = "creación equilibrada" if creacion == "equilibrada" else f"creación por {creacion}"
    texto = (f"{club['formacion']}, {club['estilo_defensivo']} en defensa, {construccion} y {creacion}"
             + (f"; {', '.join(rasgos)}" if rasgos else ""))
    return {"formacion": club["formacion"], "estilo_defensivo": club["estilo_defensivo"],
            "construccion": club["construccion"], "creacion_ocasiones": club["creacion_ocasiones"],
            "descripcion": texto, "entrenador": club.get("entrenador", "")}


def pesos_para(posicion, club):
    """Pesos de cada atributo para una posición en un club concreto (base + ajustes de estilo)."""
    pesos = dict(PESOS_BASE[posicion])

    def sumar(ajuste):
        for atributo, extra in ajuste.items():
            pesos[atributo] = pesos.get(atributo, 0) + extra

    if posicion != "POR":
        for (campo, valor), por_posicion in AJUSTES_ESTILO.items():
            if club.get(campo) == valor:
                sumar(por_posicion.get(posicion, por_posicion.get("*", {})))
        if club.get("anchura_ofensiva", 0) >= ANCHURA_ALTA:
            sumar(AJUSTE_ANCHURA.get(posicion, {}))
        if club.get("jugadores_en_area", 0) >= AREA_LLENA:
            sumar(AJUSTE_AREA.get(posicion, {}))
        for rasgo in rasgos_formacion(club.get("formacion", "")):
            sumar(AJUSTES_FORMACION[rasgo].get(posicion, {}))
    elif club.get("construccion") == "construcción lenta":
        pesos["vision"] = 0.15        # portero que participa en la salida desde atrás
    return pesos


# ======================================================================
# PERFIL DEL JUGADOR
# ======================================================================
def _a(jugador, nombre):
    return jugador.get(ATRIBUTOS[nombre]) or 0


def perfil_tactico(jugador):
    """Tipo de jugador según sus atributos (reglas simples por posición)."""
    a = lambda n: _a(jugador, n)
    pos = jugador["posicion"]
    if pos == "POR":
        return "portero de juego de pies" if a("vision") >= 60 else "portero clásico"
    if pos == "DFC":
        if a("pase") >= 70:
            return "central de salida"
        if a("ritmo") >= 75:
            return "central rápido"
        return "central de marca"
    if pos == "LAT":
        return "lateral ofensivo" if a("regate") + a("pase") >= a("defensa") * 2 else "lateral defensivo"
    if pos == "MED":
        if a("defensa") >= 75 and a("defensa") >= a("vision"):
            return "pivote defensivo"
        if a("pase") >= 78 and a("vision") >= 78:
            return "organizador"
        if a("tiro") >= 75 and a("regate") >= 78:
            return "mediapunta"
        return "mediocampista mixto"
    if pos == "EXT":
        if a("ritmo") >= 85 and a("regate") >= 80:
            return "extremo desequilibrante"
        if a("tiro") >= 78:
            return "extremo goleador"
        return "extremo asociativo"
    if a("cabezazo") >= 78 and a("fisico") >= 75:
        return "delantero de área"
    if a("pase") >= 75 and a("vision") >= 75:
        return "delantero asociativo"
    return "delantero móvil"


# ======================================================================
# ENCAJE
# ======================================================================
def puntaje(jugador, pesos):
    total = sum(pesos.values())
    return round(sum(peso * _a(jugador, atributo) for atributo, peso in pesos.items()) / total, 1)


def encaje_tactico(jugador, club, plantilla_club):
    """Puntaje 0-100 del jugador para el estilo del club, comparado con el mejor titular de su posición."""
    pesos = pesos_para(jugador["posicion"], club)
    valor = puntaje(jugador, pesos)
    nivel = next(n for minimo, n in NIVELES_ENCAJE if valor >= minimo)
    # Motivos: los atributos que más aportan al puntaje (peso x valor)
    aportes = sorted(pesos, key=lambda at: pesos[at] * _a(jugador, at), reverse=True)[:2]
    motivos = [f"{at} {_a(jugador, at)}" for at in aportes]
    propios = [j for j in plantilla_club if j["posicion"] == jugador["posicion"] and j["id"] != jugador["id"]]
    referencia = max(propios, key=lambda j: j["rating"], default=None)
    return {
        "perfil_tactico": perfil_tactico(jugador),
        "encaje_tactico": valor,
        "nivel_encaje": nivel,
        "atributos_clave_para_el_estilo": motivos,
        "encaje_del_mejor_actual": puntaje(referencia, pesos) if referencia else None,
        "perfil_del_mejor_actual": perfil_tactico(referencia) if referencia else None,
    }