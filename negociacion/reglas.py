"""Reglas de la negociación con el club vendedor: lo que decide el código (el árbitro).

El Selling Club Agent (LLM) propone; estas funciones calculan la información privada del
vendedor, valoran cada oferta y corrigen cualquier decisión del modelo que rompa las reglas.
Todas las ponderaciones están en config.py.

Formato de una oferta (diccionario):
    {"fijo": 30.0, "variables": 5.0, "pct_reventa": 10, "recompra_pct": 0,
     "recompra_temporadas": 0, "cuotas": 1, "clausula": False}
    Montos en millones de euros. "fijo" se paga en "cuotas" pagos anuales iguales.
"""
import re

from config import (
    ANIOS_CONTRATO_INTRANSFERIBLE, CONCESION_RESPALDO, DIAS_RESPUESTA_MIN, EDAD_JOVEN, EDAD_VETERANO,
    FACTOR_PRECIO_PEDIDO, FACTOR_VALOR_RECOMPRA, FACTOR_VALOR_REVENTA, MARGEN_JOVEN_POTENCIAL,
    MAX_CUOTAS, MAX_PCT_RECOMPRA, MAX_PCT_REVENTA, MAX_RONDAS_CLUB, PESO_CAPITAN, PESO_CONTRATO,
    PESO_JOVEN_CON_POTENCIAL, PESO_MEJOR_DE_SU_POSICION, PESO_TITULAR, PESO_VARIABLES,
    PESO_VENTA_RIVAL, PESO_VETERANO, TASA_DESCUENTO, UMBRAL_OFERTA_INICIAL, UMBRAL_OFERTA_RIDICULA,
    UMBRAL_RUPTURA_LLM,
)

OFERTA_VACIA = {"fijo": 0.0, "variables": 0.0, "pct_reventa": 0, "recompra_pct": 0,
                "recompra_temporadas": 0, "cuotas": 1, "clausula": False}


# ======================================================================
# OFERTAS
# ======================================================================
def normalizar_oferta(oferta):
    """Completa los campos que faltan y fuerza cada valor a un rango válido."""
    o = {**OFERTA_VACIA, **{k: v for k, v in (oferta or {}).items() if v is not None}}

    def num(x, minimo=0.0, maximo=None):
        try:
            x = float(x)
        except (TypeError, ValueError):
            x = 0.0
        x = max(minimo, x)
        return min(x, maximo) if maximo is not None else x

    o["fijo"] = round(num(o["fijo"]), 2)
    o["variables"] = round(num(o["variables"]), 2)
    o["pct_reventa"] = int(num(o["pct_reventa"], 0, MAX_PCT_REVENTA))
    o["recompra_pct"] = int(num(o["recompra_pct"], 0, MAX_PCT_RECOMPRA))
    o["recompra_temporadas"] = int(num(o["recompra_temporadas"], 0, 5)) if o["recompra_pct"] else 0
    o["clausula"] = bool(o["clausula"])
    o["cuotas"] = 1 if o["clausula"] else int(num(o["cuotas"], 1, MAX_CUOTAS))
    return {k: o[k] for k in OFERTA_VACIA}


def valor_presente(monto, cuotas):
    """Valor hoy de 'monto' pagado en 'cuotas' pagos anuales iguales (el primero hoy)."""
    cuota = monto / cuotas
    return sum(cuota / (1 + TASA_DESCUENTO) ** t for t in range(cuotas))


def valor_efectivo(oferta, valor_referencia):
    """Cuánto vale una oferta para el club vendedor, en millones de euros de hoy."""
    o = normalizar_oferta(oferta)
    valor = valor_presente(o["fijo"], o["cuotas"])
    valor += PESO_VARIABLES * o["variables"]
    valor += o["pct_reventa"] / 100 * valor_referencia * FACTOR_VALOR_REVENTA
    if o["recompra_temporadas"]:
        valor += o["recompra_pct"] / 100 * valor_referencia * FACTOR_VALOR_RECOMPRA
    return round(valor, 2)


def primer_pago(oferta):
    """Lo que sale del presupuesto en esta ventana: la primera cuota (o la cláusula completa)."""
    o = normalizar_oferta(oferta)
    return round(o["fijo"] / o["cuotas"], 2)


def describir_oferta(oferta):
    """Texto corto y humano de una oferta, para mostrar al usuario."""
    o = normalizar_oferta(oferta)
    if o["clausula"]:
        return f"pago de la cláusula: {o['fijo']} M€ al contado"
    partes = [f"{o['fijo']} M€ fijos" + (f" en {o['cuotas']} cuotas anuales" if o["cuotas"] > 1 else "")]
    if o["variables"]:
        partes.append(f"{o['variables']} M€ en variables")
    if o["pct_reventa"]:
        partes.append(f"{o['pct_reventa']} % de una futura venta")
    if o["recompra_pct"] and o["recompra_temporadas"]:
        partes.append(f"opción de recompra reteniendo el {o['recompra_pct']} % durante "
                      f"{o['recompra_temporadas']} temporada(s)")
    return ", ".join(partes)


# ======================================================================
# INFORMACIÓN PRIVADA DEL VENDEDOR
# ======================================================================
def perfil_vendedor(jugador, plantilla_vendedor, club_vendedor, club_comprador):
    """Calcula el precio mínimo, el precio pedido y si el jugador es intransferible.

    jugador: fila de jugadores.csv | plantilla_vendedor: plantilla de su club
    club_vendedor / club_comprador: filas de clubes.csv
    """
    valor = jugador["valor_mercado"]
    factores = []

    def aplicar(peso, motivo):
        nonlocal valor
        valor *= peso
        factores.append(f"{motivo} x{peso:.2f}")

    misma_posicion = [j for j in plantilla_vendedor if j["posicion"] == jugador["posicion"]]
    es_mejor = jugador["rating"] >= max((j["rating"] for j in misma_posicion), default=0)
    es_titular = jugador["titular"] == "si"
    es_rival = (club_vendedor["rival"] == club_comprador["club"]
                or club_comprador["rival"] == club_vendedor["club"])

    if es_titular:
        aplicar(PESO_TITULAR, "titular")
    if es_mejor:
        aplicar(PESO_MEJOR_DE_SU_POSICION, "mejor de su posición")
    if jugador["anios_contrato"] in PESO_CONTRATO:
        aplicar(PESO_CONTRATO[jugador["anios_contrato"]], f"{jugador['anios_contrato']} año(s) de contrato")
    if jugador["edad"] >= EDAD_VETERANO:
        aplicar(PESO_VETERANO, "veterano")
    elif jugador["edad"] <= EDAD_JOVEN and jugador["potencial"] >= jugador["rating"] + MARGEN_JOVEN_POTENCIAL:
        aplicar(PESO_JOVEN_CON_POTENCIAL, "joven con potencial")
    if es_rival:
        aplicar(PESO_VENTA_RIVAL, "venta a un rival")
    if jugador.get("capitan") == "si":
        aplicar(PESO_CAPITAN, "capitán")

    clausula = jugador.get("clausula_rescision") or 0
    minimo = round(min(valor, clausula) if clausula else valor, 2)
    pedido = round(min(minimo * FACTOR_PRECIO_PEDIDO, clausula) if clausula else minimo * FACTOR_PRECIO_PEDIDO, 2)
    intransferible = (es_titular and es_mejor
                      and jugador["anios_contrato"] >= ANIOS_CONTRATO_INTRANSFERIBLE
                      and club_vendedor["nivel"] >= club_comprador["nivel"])
    return {
        "valor_referencia": jugador["valor_mercado"],
        "precio_minimo": minimo,
        "precio_pedido": max(pedido, minimo),
        "clausula": clausula,
        "intransferible": intransferible,
        "es_titular": es_titular,
        "es_mejor_de_su_posicion": es_mejor,
        "es_rival": es_rival,
        "factores": factores,
    }


def oferta_de_pedido(perfil):
    """La exigencia inicial del vendedor como oferta: el precio pedido, fijo y al contado."""
    return normalizar_oferta({"fijo": perfil["precio_pedido"]})


# ======================================================================
# OFERTA INICIAL
# ======================================================================
def evaluar_oferta_inicial(intencion, oferta, perfil):
    """Decide (con reglas) la respuesta del club al primer contacto y cuántos días tarda.

    intencion: "interes" (sin cifras), "oferta" o "clausula".
    Devuelve {"resultado": abre | rechaza | solo_clausula | acepta_clausula, "dias": n, "motivo": texto}
    """
    importante = perfil["es_titular"] and perfil["es_mejor_de_su_posicion"]
    dias = DIAS_RESPUESTA_MIN + (1 if importante else 0)

    if intencion == "clausula":
        return {"resultado": "acepta_clausula", "dias": DIAS_RESPUESTA_MIN,
                "motivo": "la cláusula obliga al club a aceptar"}
    if perfil["intransferible"]:
        return {"resultado": "solo_clausula", "dias": dias + 1,
                "motivo": "el jugador es intransferible: solo sale pagando la cláusula"}
    if intencion == "interes":
        return {"resultado": "abre", "dias": dias + 1, "motivo": "interés sin oferta: el club fija sus condiciones"}

    proporcion = valor_efectivo(oferta, perfil["valor_referencia"]) / perfil["precio_minimo"]
    if proporcion < UMBRAL_OFERTA_RIDICULA:
        return {"resultado": "rechaza", "dias": DIAS_RESPUESTA_MIN, "motivo": "oferta muy lejos del valor del jugador"}
    if proporcion < UMBRAL_OFERTA_INICIAL:
        return {"resultado": "rechaza", "dias": dias + 1, "motivo": "oferta insuficiente para abrir negociaciones"}
    return {"resultado": "abre", "dias": dias + (0 if proporcion >= 1 else 1),
            "motivo": "oferta razonable: el club acepta negociar"}


# ======================================================================
# RONDAS: REGLA DE RESPALDO Y ÁRBITRO
# ======================================================================
def peticion_respaldo(perfil, ronda):
    """Regla simple de concesión: parte del precio pedido y llega al mínimo en la última ronda.
    Concede poco al inicio y más al final (forma controlada por CONCESION_RESPALDO)."""
    avance = min(1.0, ronda / MAX_RONDAS_CLUB) ** CONCESION_RESPALDO
    monto = perfil["precio_pedido"] - (perfil["precio_pedido"] - perfil["precio_minimo"]) * avance
    return normalizar_oferta({"fijo": round(monto, 2)})


def decision_respaldo(oferta_comprador, perfil, ronda, ultima_peticion):
    """Lo que haría la regla simple en esta ronda (también es la línea base de la evaluación)."""
    valor = valor_efectivo(oferta_comprador, perfil["valor_referencia"])
    peticion = peticion_respaldo(perfil, ronda)
    if ultima_peticion and valor_efectivo(peticion, perfil["valor_referencia"]) > \
            valor_efectivo(ultima_peticion, perfil["valor_referencia"]):
        peticion = normalizar_oferta(ultima_peticion)
    if valor >= valor_efectivo(peticion, perfil["valor_referencia"]) or \
            (ronda >= MAX_RONDAS_CLUB and valor >= perfil["precio_minimo"]):
        return {"accion": "aceptar", "contraoferta": None}
    if ronda >= MAX_RONDAS_CLUB:
        return {"accion": "rechazar", "contraoferta": None}
    return {"accion": "contraofertar", "contraoferta": peticion}


def revela_minimo(mensaje, perfil, cifras_permitidas=()):
    """True si el mensaje contiene el precio mínimo (y no es una cifra que el club sí ofreció)."""
    minimo = perfil["precio_minimo"]
    for texto in re.findall(r"\d+(?:[.,]\d+)?", mensaje or ""):
        numero = float(texto.replace(",", "."))
        if abs(numero - minimo) < 0.05 and all(abs(numero - c) >= 0.05 for c in cifras_permitidas):
            return True
    return False


def arbitrar(decision, oferta_comprador, perfil, ronda, ultima_peticion):
    """Revisa la decisión del Selling Club Agent y la corrige si rompe una regla.

    Devuelve (decision_final, correcciones) donde correcciones es una lista de textos
    (vacía si el modelo respetó todas las reglas).
    """
    ref = perfil["valor_referencia"]
    valor_oferta = valor_efectivo(oferta_comprador, ref)
    correcciones = []
    accion = (decision or {}).get("accion")
    contra = (decision or {}).get("contraoferta")

    if accion not in ("aceptar", "contraofertar", "rechazar"):
        correcciones.append("respuesta del modelo inválida: decide la regla de respaldo")
        return decision_respaldo(oferta_comprador, perfil, ronda, ultima_peticion), correcciones

    # Regla 1: no se acepta bajo el mínimo
    if accion == "aceptar" and valor_oferta < perfil["precio_minimo"]:
        correcciones.append("el modelo aceptó bajo el precio mínimo")
        accion, contra = "contraofertar", None

    # Regla 2: solo se rompe si la oferta es realmente baja; en la última ronda se acepta o se rechaza
    if accion == "rechazar" and ronda < MAX_RONDAS_CLUB and valor_oferta >= UMBRAL_RUPTURA_LLM * perfil["precio_minimo"]:
        correcciones.append("el modelo rompió con una oferta razonable: se convierte en contraoferta")
        accion, contra = "contraofertar", None
    if accion == "contraofertar" and ronda >= MAX_RONDAS_CLUB:
        accion = "aceptar" if valor_oferta >= perfil["precio_minimo"] else "rechazar"
        correcciones.append("última ronda: el club debe aceptar o rechazar")
        contra = None

    if accion == "contraofertar":
        if not contra or normalizar_oferta(contra)["fijo"] <= 0:
            contra = peticion_respaldo(perfil, ronda)
            correcciones.append("contraoferta vacía: se usa la regla de respaldo")
        contra = normalizar_oferta(contra)
        if contra["clausula"]:
            contra["clausula"] = False
        valor_contra = valor_efectivo(contra, ref)
        # Regla 3: nunca pide más que en su ronda anterior (consistencia / compromiso)
        if ultima_peticion and valor_contra > valor_efectivo(ultima_peticion, ref) + 0.01:
            contra = normalizar_oferta(ultima_peticion)
            correcciones.append("el modelo pidió más que en la ronda anterior")
            valor_contra = valor_efectivo(contra, ref)
        # Regla 4: nunca pide menos que su mínimo
        if valor_contra < perfil["precio_minimo"]:
            contra["fijo"] = round(contra["fijo"] + (perfil["precio_minimo"] - valor_contra) + 0.01, 2)
            correcciones.append("la contraoferta quedaba bajo el precio mínimo")
            valor_contra = valor_efectivo(contra, ref)
        # Regla 5: si su contraoferta no supera lo ofrecido, en realidad está aceptando
        if valor_contra <= valor_oferta:
            accion, contra = "aceptar", None
            correcciones.append("la contraoferta no superaba la oferta del comprador: se acepta")

    return {"accion": accion, "contraoferta": contra if accion == "contraofertar" else None}, correcciones


def es_ridicula(oferta, perfil):
    return valor_efectivo(oferta, perfil["valor_referencia"]) < UMBRAL_OFERTA_RIDICULA * perfil["precio_minimo"]


# ======================================================================
# DESEMPEÑO
# ======================================================================
def desempeno(perfil, precio_acordado=None, ultima_oferta=None):
    """Compara el resultado con el rango que existía entre el mínimo y el pedido del vendedor."""
    minimo, pedido = perfil["precio_minimo"], perfil["precio_pedido"]
    ref = perfil["valor_referencia"]
    if precio_acordado is not None:
        pagado = valor_efectivo(precio_acordado, ref)
        rango = max(pedido - minimo, 0.01)
        captura = max(0.0, min(1.0, (pedido - pagado) / rango))
        return {"resultado": "acuerdo", "precio_minimo": minimo, "precio_pedido": pedido,
                "valor_pagado": pagado, "captura_pct": round(100 * captura),
                "sobrepago": round(pagado - minimo, 2)}
    ultimo = valor_efectivo(ultima_oferta, ref) if ultima_oferta else 0
    return {"resultado": "fracaso", "precio_minimo": minimo, "precio_pedido": pedido,
            "ultima_oferta_valor": ultimo, "faltaron": round(max(0.0, minimo - ultimo), 2)}
