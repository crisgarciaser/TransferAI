"""Ventas de jugadores propios: ofertas de otros clubes y reglas del club comprador (árbitro).

El club comprador tiene un precio máximo privado. El agente de club (rol comprador) decide cada
ronda y estas funciones corrigen cualquier decisión que rompa las reglas.
"""
import random

from config import (
    DIA_LIMITE_OFERTAS_VENTA, MAX_OFERTAS_POR_JUGADOR, MAX_RONDAS_VENTA, MIN_JUGADORES_PLANTILLA,
    OFERTA_INICIAL_COMPRADOR, PESO_NECESIDAD_ALTA, PESO_NECESIDAD_MEDIA, PESO_QUITAR_AL_RIVAL,
    PROB_OFERTA_ESPONTANEA, PROB_OFERTA_TRANSFERIBLE, SEMILLA_MERCADO, UMBRAL_RIDICULO_VENTA,
)
from datos import cargar_clubes, obtener_plantilla
from negociacion.reglas import normalizar_oferta, valor_efectivo

azar = random.Random(SEMILLA_MERCADO)


# ======================================================================
# QUIÉN PUEDE VENDERSE Y QUIÉN COMPRA
# ======================================================================
def vendibles(estado):
    """Jugadores propios que se pueden vender (ni fichados en esta ventana ni cedidos al club)."""
    plantilla = obtener_plantilla(estado["club"])
    if len(plantilla) <= MIN_JUGADORES_PLANTILLA:
        return []
    fichados = {f["id"] for f in estado.get("fichajes", [])}
    return [j for j in plantilla if j["id"] not in fichados and not j.get("cedido_por")]


def perfil_comprador(jugador, club_comprador, club_vendedor):
    """Precio máximo (privado) y primera oferta del club comprador."""
    propios = [j for j in obtener_plantilla(club_comprador["club"]) if j["posicion"] == jugador["posicion"]]
    mejor = max((j["rating"] for j in propios), default=0)
    valor = jugador["valor_mercado"]
    factores = []
    if jugador["rating"] >= mejor + 3:
        valor *= PESO_NECESIDAD_ALTA
        factores.append(f"necesidad alta x{PESO_NECESIDAD_ALTA}")
    else:
        valor *= PESO_NECESIDAD_MEDIA
        factores.append(f"necesidad media x{PESO_NECESIDAD_MEDIA}")
    if club_comprador["rival"] == club_vendedor["club"]:
        valor *= PESO_QUITAR_AL_RIVAL
        factores.append(f"jugador del rival x{PESO_QUITAR_AL_RIVAL}")
    maximo = round(min(valor, club_comprador["presupuesto_fichajes"]), 2)
    inicial = round(min(jugador["valor_mercado"] * azar.uniform(*OFERTA_INICIAL_COMPRADOR), 0.9 * maximo), 2)
    return {"valor_referencia": jugador["valor_mercado"], "precio_maximo": maximo, "oferta_inicial": inicial,
            "factores": factores}


def compradores_interesados(jugador, club_usuario, excluir=()):
    """Clubes a los que el jugador les sirve (iguala o mejora a su mejor en la posición) y que pueden pagarlo."""
    interesados = []
    for c in cargar_clubes():
        if c["club"] in (club_usuario, *excluir) or c["presupuesto_fichajes"] < 0.8 * jugador["valor_mercado"]:
            continue
        propios = [j for j in obtener_plantilla(c["club"]) if j["posicion"] == jugador["posicion"]]
        if jugador["rating"] >= max((j["rating"] for j in propios), default=0):
            interesados.append(c)
    return interesados


# ======================================================================
# GENERACIÓN DE OFERTAS (se llama una vez por cada día que avanza)
# ======================================================================
def generar_ofertas(estado, dia, ofertas):
    """Devuelve las ofertas nuevas del día: por jugadores transferibles y espontáneas."""
    clubes = {c["club"]: c for c in cargar_clubes()}
    club_usuario = clubes[estado["club"]]
    candidatos = {j["id"]: j for j in vendibles(estado)}
    nuevas = []

    def crear(jugador, motivo):
        ya = [o for o in ofertas + nuevas if o["jugador"]["id"] == jugador["id"]]
        if len(ya) >= MAX_OFERTAS_POR_JUGADOR:
            return
        opciones = compradores_interesados(jugador, estado["club"], excluir=[o["club_comprador"] for o in ya])
        if not opciones:
            return
        comprador = azar.choice(opciones)
        perfil = perfil_comprador(jugador, comprador, club_usuario)
        nuevas.append({"id": f"{jugador['id']}-{comprador['club']}", "jugador": jugador,
                       "club_comprador": comprador["club"], "perfil": perfil, "dia": dia, "motivo": motivo,
                       "oferta": normalizar_oferta({"fijo": perfil["oferta_inicial"]}),
                       "fase": "pendiente", "ronda": 0, "historial": []})

    # Transferibles: la probabilidad cae desde el día 1 hasta el día límite
    if dia <= DIA_LIMITE_OFERTAS_VENTA:
        prob = PROB_OFERTA_TRANSFERIBLE * (1 - (dia - 1) / DIA_LIMITE_OFERTAS_VENTA)
        for id_jugador in estado.get("transferibles", []):
            if id_jugador in candidatos and azar.random() < prob:
                crear(candidatos[id_jugador], "transferible")
    # Oferta espontánea por algún jugador del plantel (más probable por los mejores)
    if candidatos and azar.random() < PROB_OFERTA_ESPONTANEA:
        lista = sorted(candidatos.values(), key=lambda j: j["valor_mercado"], reverse=True)[:12]
        crear(azar.choice(lista), "espontanea")
    return nuevas


# ======================================================================
# RONDAS: REGLA DE RESPALDO Y ÁRBITRO DEL COMPRADOR
# ======================================================================
def oferta_respaldo(perfil, ronda):
    """El comprador sube desde su oferta inicial hasta su máximo en la última ronda."""
    avance = min(1.0, ronda / MAX_RONDAS_VENTA) ** 1.5
    monto = perfil["oferta_inicial"] + (perfil["precio_maximo"] - perfil["oferta_inicial"]) * avance
    return normalizar_oferta({"fijo": round(monto, 2)})


def es_ridiculo(pedido, perfil):
    return valor_efectivo(pedido, perfil["valor_referencia"]) > UMBRAL_RIDICULO_VENTA * perfil["precio_maximo"]


def arbitrar_compra(decision, pedido, perfil, ronda, ultima_oferta):
    """Revisa la decisión del comprador. Devuelve (decision_final, correcciones)."""
    ref = perfil["valor_referencia"]
    valor_pedido = valor_efectivo(pedido, ref)
    correcciones = []
    accion = (decision or {}).get("accion")
    contra = (decision or {}).get("contraoferta")
    if accion not in ("aceptar", "contraofertar", "rechazar"):
        correcciones.append("respuesta del modelo inválida: decide la regla de respaldo")
        accion, contra = "contraofertar", oferta_respaldo(perfil, ronda)
    if accion == "aceptar" and valor_pedido > perfil["precio_maximo"]:
        correcciones.append("el comprador aceptó por encima de su precio máximo")
        accion, contra = "contraofertar", None
    if accion == "rechazar" and ronda < MAX_RONDAS_VENTA and valor_pedido <= 1.3 * perfil["precio_maximo"]:
        correcciones.append("el comprador se retiró con un pedido razonable: se convierte en contraoferta")
        accion, contra = "contraofertar", None
    if accion == "contraofertar" and ronda >= MAX_RONDAS_VENTA:
        accion = "aceptar" if valor_pedido <= perfil["precio_maximo"] else "rechazar"
        correcciones.append("última ronda: el comprador debe aceptar o retirarse")
        contra = None
    if accion == "contraofertar":
        contra = normalizar_oferta(contra) if contra else oferta_respaldo(perfil, ronda)
        if contra["fijo"] <= 0:
            contra = oferta_respaldo(perfil, ronda)
        if ultima_oferta and valor_efectivo(contra, ref) < valor_efectivo(ultima_oferta, ref) - 0.01:
            contra = normalizar_oferta(ultima_oferta)
            correcciones.append("el comprador bajó su oferta anterior")
        exceso = valor_efectivo(contra, ref) - perfil["precio_maximo"]
        if exceso > 0:
            contra["fijo"] = round(max(contra["fijo"] - exceso - 0.01, 0), 2)
            correcciones.append("la contraoferta superaba su precio máximo")
        if valor_efectivo(contra, ref) >= valor_pedido:
            accion, contra = "aceptar", None
            correcciones.append("la contraoferta igualaba lo pedido: se acepta")
    return {"accion": accion, "contraoferta": contra if accion == "contraofertar" else None}, correcciones


def revela_maximo(mensaje, perfil, cifras_permitidas=()):
    from negociacion.reglas import revela_minimo
    return revela_minimo(mensaje, {"precio_minimo": perfil["precio_maximo"]}, cifras_permitidas)


def desempeno_venta(perfil, acuerdo):
    """Cuánto del margen del comprador (de su primera oferta a su máximo) capturó el vendedor."""
    cobrado = valor_efectivo(acuerdo, perfil["valor_referencia"])
    rango = max(perfil["precio_maximo"] - perfil["oferta_inicial"], 0.01)
    captura = max(0.0, min(1.0, (cobrado - perfil["oferta_inicial"]) / rango))
    return {"oferta_inicial": perfil["oferta_inicial"], "precio_maximo": perfil["precio_maximo"],
            "valor_cobrado": cobrado, "captura_pct": round(100 * captura)}