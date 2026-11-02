"""Reglas de la negociación con el jugador: lo que decide el código (el árbitro).

El Player Agent (LLM) propone; estas funciones calculan la exigencia privada del jugador,
valoran cada oferta y corrigen cualquier decisión del modelo que rompa las reglas.
Todas las ponderaciones están en config.py.

Formato de una oferta al jugador (diccionario):
    {"salario": 3.0, "bonos": {"goles": 0.5}, "anios": 4, "anio_opcional": True, "prima": 1.0}
    salario y bonos en millones de euros por temporada; prima: pago único al firmar.
"""
import re
from collections import Counter

from config import (
    ANIOS_ADULTO, ANIOS_JOVEN_CLUB_GRANDE, ANIOS_JOVEN_CLUB_PEQUENO, ANIOS_VETERANO, CONCESION_ESTRELLA,
    CONCESION_JUGADOR, EDAD_JOVEN, EDAD_VETERANO, FACTOR_PEDIDO_JUGADOR, MAX_ANIOS_CONTRATO,
    MAX_RONDAS_JUGADOR, N_AGENCIAS_GRANDES, NIVEL_CLUB_GRANDE, ORDEN_POSICIONES_BONO, PENALIZACION_POR_ANIO,
    PESO_AGENCIA_GRANDE, PESO_BAJAR_NIVEL, PESO_CAMBIO_DE_CLUB, PESO_ESTRELLA, PESO_GANA_EUROPA,
    PESO_PIERDE_EUROPA, PESO_ROTACION, PROB_BONO, TIPOS_BONO, UMBRAL_RUPTURA_ESTRELLA, UMBRAL_RUPTURA_JUGADOR,
    VALOR_ANIO_OPCIONAL,
)
from datos import cargar_jugadores, es_estrella

OFERTA_JUGADOR_VACIA = {"salario": 0.0, "bonos": {}, "anios": 0, "anio_opcional": False, "prima": 0.0}


# ======================================================================
# OFERTAS
# ======================================================================
def normalizar_oferta_jugador(oferta):
    o = {**OFERTA_JUGADOR_VACIA, **{k: v for k, v in (oferta or {}).items() if v is not None}}

    def num(x):
        try:
            return max(0.0, float(x))
        except (TypeError, ValueError):
            return 0.0

    bonos = {}
    for tipo, monto in (o.get("bonos") or {}).items():
        if tipo in TIPOS_BONO and num(monto) > 0:
            bonos[tipo] = round(num(monto), 2)
    anios = int(min(num(o["anios"]), MAX_ANIOS_CONTRATO))
    return {"salario": round(num(o["salario"]), 3), "bonos": bonos, "anios": anios,
            "anio_opcional": bool(o["anio_opcional"]) and anios > 0, "prima": round(num(o["prima"]), 2)}


def valor_bonos(bonos, posicion):
    """Valor esperado anual de los bonos: monto x probabilidad de cumplirlo según la posición."""
    i = ORDEN_POSICIONES_BONO.index(posicion)
    return round(sum(monto * PROB_BONO[tipo][i] for tipo, monto in (bonos or {}).items()), 3)


def bonos_poco_probables(bonos, posicion):
    """Bonos que casi no tienen sentido para la posición (probabilidad menor a 10 %)."""
    i = ORDEN_POSICIONES_BONO.index(posicion)
    return [t for t in (bonos or {}) if PROB_BONO[t][i] < 0.10]


def anios_efectivos(oferta):
    return oferta["anios"] + (VALOR_ANIO_OPCIONAL if oferta["anio_opcional"] else 0)


def valor_anual_para_jugador(oferta, posicion):
    """Lo que vale la oferta por temporada para el jugador: salario + bonos esperados + prima repartida."""
    o = normalizar_oferta_jugador(oferta)
    anios = max(anios_efectivos(o), 1)
    return round(o["salario"] + valor_bonos(o["bonos"], posicion) + o["prima"] / anios, 3)


def costo_anual_club(oferta, posicion):
    """Lo que ocupa la oferta en la masa salarial: salario + bonos esperados (la prima sale del presupuesto)."""
    o = normalizar_oferta_jugador(oferta)
    return round(o["salario"] + valor_bonos(o["bonos"], posicion), 3)


def describir_oferta_jugador(oferta):
    o = normalizar_oferta_jugador(oferta)
    texto = f"{o['salario']} M€ por temporada durante {o['anios']} año(s)" + (" + 1 opcional" if o["anio_opcional"] else "")
    if o["bonos"]:
        texto += ", bonos por " + ", ".join(f"{t.replace('_', ' ')} ({m} M€)" for t, m in o["bonos"].items())
    if o["prima"]:
        texto += f", prima de fichaje de {o['prima']} M€"
    return texto


# ======================================================================
# INFORMACIÓN PRIVADA DEL JUGADOR
# ======================================================================
def agencias_grandes():
    conteo = Counter(j["agencia"] for j in cargar_jugadores() if j.get("agencia"))
    return {a for a, _ in conteo.most_common(N_AGENCIAS_GRANDES)}


def anios_preferidos(jugador, club_comprador):
    if jugador["edad"] < EDAD_JOVEN:
        return ANIOS_JOVEN_CLUB_GRANDE if club_comprador["nivel"] >= NIVEL_CLUB_GRANDE else ANIOS_JOVEN_CLUB_PEQUENO
    if jugador["edad"] >= EDAD_VETERANO:
        return ANIOS_VETERANO
    return ANIOS_ADULTO


def perfil_jugador(jugador, club_vendedor, club_comprador, sera_titular):
    """Exigencia salarial mínima, exigencia inicial, años preferidos y dureza del jugador (privado)."""
    salario = jugador["salario_anual"]
    factores = []

    def aplicar(peso, motivo):
        nonlocal salario
        if peso != 1:
            salario *= peso
            factores.append(f"{motivo} x{peso:.2f}")

    aplicar(PESO_CAMBIO_DE_CLUB, "cambio de club")
    bajada = club_vendedor["nivel"] - club_comprador["nivel"]
    if bajada > 0:
        aplicar(1 + PESO_BAJAR_NIVEL * bajada, f"baja {bajada} nivel(es) de club")
    europa_v = club_vendedor["competicion_internacional"] != "no"
    europa_c = club_comprador["competicion_internacional"] != "no"
    if europa_v and not europa_c:
        aplicar(PESO_PIERDE_EUROPA, "pierde competición europea")
    elif europa_c and not europa_v:
        aplicar(PESO_GANA_EUROPA, "gana competición europea")
    if not sera_titular:
        aplicar(PESO_ROTACION, "rol de rotación")
    estrella = es_estrella(jugador)
    if estrella:
        aplicar(PESO_ESTRELLA, "estrella")
    if jugador.get("agencia") in agencias_grandes():
        aplicar(PESO_AGENCIA_GRANDE, "agencia grande")

    minimo = round(salario, 3)
    return {
        "salario_actual": jugador["salario_anual"],
        "salario_minimo": minimo,
        "salario_pedido": round(minimo * FACTOR_PEDIDO_JUGADOR, 3),
        "anios_preferidos": list(anios_preferidos(jugador, club_comprador)),
        "estrella": estrella,
        "sera_titular": sera_titular,
        "posicion": jugador["posicion"],
        "umbral_ruptura": UMBRAL_RUPTURA_ESTRELLA if estrella else UMBRAL_RUPTURA_JUGADOR,
        "concesion": CONCESION_ESTRELLA if estrella else CONCESION_JUGADOR,
        "factores": factores,
    }


def minimo_para_anios(perfil, oferta):
    """Mínimo anual que exige el jugador para la duración ofrecida (castiga salirse de su rango)."""
    lo, hi = perfil["anios_preferidos"]
    anios = anios_efectivos(normalizar_oferta_jugador(oferta))
    distancia = max(0.0, lo - anios, anios - hi)
    return round(perfil["salario_minimo"] * (1 + PENALIZACION_POR_ANIO * distancia), 3)


def proporcion(oferta, perfil):
    """Cuánto cubre la oferta de lo que exige el jugador (1 = justo su mínimo)."""
    return valor_anual_para_jugador(oferta, perfil["posicion"]) / max(minimo_para_anios(perfil, oferta), 0.001)


def peticion_inicial(perfil):
    return normalizar_oferta_jugador({"salario": perfil["salario_pedido"], "anios": perfil["anios_preferidos"][1]})


# ======================================================================
# RONDAS: REGLA DE RESPALDO Y ÁRBITRO
# ======================================================================
def peticion_respaldo(perfil, ronda):
    avance = min(1.0, ronda / MAX_RONDAS_JUGADOR) ** perfil["concesion"]
    salario = perfil["salario_pedido"] - (perfil["salario_pedido"] - perfil["salario_minimo"]) * avance
    return normalizar_oferta_jugador({"salario": round(salario, 3), "anios": perfil["anios_preferidos"][1]})


def decision_respaldo(oferta, perfil, ronda, ultima_peticion):
    pos = perfil["posicion"]
    peticion = peticion_respaldo(perfil, ronda)
    if ultima_peticion and valor_anual_para_jugador(peticion, pos) > valor_anual_para_jugador(ultima_peticion, pos):
        peticion = normalizar_oferta_jugador(ultima_peticion)
    if valor_anual_para_jugador(oferta, pos) >= valor_anual_para_jugador(peticion, pos) and proporcion(oferta, perfil) >= 1:
        return {"accion": "aceptar", "contraoferta": None}
    if ronda >= MAX_RONDAS_JUGADOR:
        return {"accion": "aceptar" if proporcion(oferta, perfil) >= 1 else "rechazar", "contraoferta": None}
    return {"accion": "contraofertar", "contraoferta": peticion}


def es_ridicula_jugador(oferta, perfil):
    return proporcion(oferta, perfil) < perfil["umbral_ruptura"] * 0.75


def arbitrar_jugador(decision, oferta, perfil, ronda, ultima_peticion):
    """Revisa la decisión del Player Agent. Devuelve (decision_final, correcciones)."""
    pos = perfil["posicion"]
    correcciones = []
    accion = (decision or {}).get("accion")
    contra = (decision or {}).get("contraoferta")
    cubre = proporcion(oferta, perfil)

    if accion not in ("aceptar", "contraofertar", "rechazar"):
        correcciones.append("respuesta del modelo inválida: decide la regla de respaldo")
        return decision_respaldo(oferta, perfil, ronda, ultima_peticion), correcciones
    if accion == "aceptar" and cubre < 1:
        correcciones.append("el modelo aceptó bajo la exigencia mínima del jugador")
        accion, contra = "contraofertar", None
    if accion == "rechazar" and ronda < MAX_RONDAS_JUGADOR and cubre >= perfil["umbral_ruptura"]:
        correcciones.append("el modelo rompió con una oferta razonable: se convierte en contraoferta")
        accion, contra = "contraofertar", None
    if accion == "contraofertar" and ronda >= MAX_RONDAS_JUGADOR:
        accion = "aceptar" if cubre >= 1 else "rechazar"
        correcciones.append("última ronda: el jugador debe aceptar o rechazar")
        contra = None

    if accion == "contraofertar":
        contra = normalizar_oferta_jugador(contra)
        if contra["salario"] <= 0 or contra["anios"] <= 0:
            contra = peticion_respaldo(perfil, ronda)
            correcciones.append("contraoferta incompleta: se usa la regla de respaldo")
        if ultima_peticion and valor_anual_para_jugador(contra, pos) > valor_anual_para_jugador(ultima_peticion, pos) + 0.001:
            contra = normalizar_oferta_jugador(ultima_peticion)
            correcciones.append("el modelo pidió más que en la ronda anterior")
        falta = minimo_para_anios(perfil, contra) - valor_anual_para_jugador(contra, pos)
        if falta > 0:
            contra["salario"] = round(contra["salario"] + falta + 0.001, 3)
            correcciones.append("la contraoferta quedaba bajo la exigencia mínima")
        if valor_anual_para_jugador(contra, pos) <= valor_anual_para_jugador(oferta, pos) and cubre >= 1:
            accion, contra = "aceptar", None
            correcciones.append("la contraoferta no superaba la oferta del club: se acepta")
    return {"accion": accion, "contraoferta": contra if accion == "contraofertar" else None}, correcciones


def revela_privado(mensaje, perfil, cifras_permitidas=()):
    """True si el mensaje contiene el salario actual o la exigencia mínima del jugador."""
    privadas = [perfil["salario_actual"], perfil["salario_minimo"]]
    for texto in re.findall(r"\d+(?:[.,]\d+)?", mensaje or ""):
        n = float(texto.replace(",", "."))
        if any(abs(n - p) < 0.05 for p in privadas) and all(abs(n - c) >= 0.05 for c in cifras_permitidas):
            return True
    return False


def desempeno_jugador(perfil, acuerdo=None, ultima_oferta=None):
    pos = perfil["posicion"]
    minimo, pedido = perfil["salario_minimo"], perfil["salario_pedido"]
    if acuerdo is not None:
        pagado = valor_anual_para_jugador(acuerdo, pos)
        captura = max(0.0, min(1.0, (pedido - pagado) / max(pedido - minimo, 0.001)))
        return {"resultado": "acuerdo", "salario_minimo": minimo, "salario_pedido": pedido,
                "valor_anual_pagado": pagado, "captura_pct": round(100 * captura),
                "salario_actual": perfil["salario_actual"]}
    ultimo = valor_anual_para_jugador(ultima_oferta, pos) if ultima_oferta else 0
    return {"resultado": "fracaso", "salario_minimo": minimo, "salario_pedido": pedido,
            "ultima_oferta_valor": ultimo, "salario_actual": perfil["salario_actual"]}
