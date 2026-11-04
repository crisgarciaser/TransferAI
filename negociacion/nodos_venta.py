"""Ventas de jugadores propios: nodos del grafo.

Flujo: menu_ventas -> (poner en venta) elegir_transferible
                   -> (responder una oferta) turno_venta -> interpretar_venta -> responder_comprador ... -> cerrar_venta
Una vez que se contraoferta no se vuelve al menú hasta el acuerdo o la ruptura.
"""
from langgraph.types import interrupt

from agentes import club_vendedor
from config import DIAS_POR_NEGOCIACION, MAX_RONDAS_VENTA
from datos import ajustar_presupuesto, obtener_plantilla, obtener_resumen_club, registrar_traspaso
from negociacion import interprete
from negociacion.nodos_club import pasar_dias
from negociacion.reglas import describir_oferta, normalizar_oferta, primer_pago, valor_efectivo
from negociacion.ventas import arbitrar_compra, desempeno_venta, es_ridiculo, revela_maximo, vendibles
from registro import emitir


def _ofertas_pendientes(estado):
    return [o for o in estado.get("ofertas_venta", {}).values() if o["fase"] == "pendiente"]


def _guardar(estado, oferta):
    return {**estado.get("ofertas_venta", {}), oferta["id"]: oferta}


def menu_ventas(estado):
    """Pausa: responder una oferta recibida o poner a un jugador en venta."""
    pendientes = _ofertas_pendientes(estado)
    transferibles = [j["nombre"] for j in obtener_plantilla(estado["club"]) if j["id"] in estado.get("transferibles", [])]
    respuesta = interrupt({
        "tipo": "menu_ventas", "dia": estado["dia"], "transferibles": transferibles,
        "ofertas": [{"jugador": o["jugador"]["nombre"], "club": o["club_comprador"],
                     "oferta": describir_oferta(o["oferta"]), "dia": o["dia"],
                     "motivo": o["motivo"]} for o in pendientes],
    })
    texto = str(respuesta).strip().lower()
    if texto in ("", "volver", "0"):
        return {"siguiente": "centro_de_mando"}
    if texto in ("vender", "v", "poner en venta"):
        return {"siguiente": "elegir_transferible"}
    if texto.isdigit() and 1 <= int(texto) <= len(pendientes):
        return {"siguiente": "turno_venta", "oferta_activa": pendientes[int(texto) - 1]["id"], "etapa": "venta"}
    emitir("aviso", "Escribe el número de una oferta, 'vender' para poner a un jugador en venta, o 'volver'.")
    return {"siguiente": "menu_ventas"}


def elegir_transferible(estado):
    """Pausa: elegir qué jugador se pone en venta."""
    candidatos = [j for j in vendibles(estado) if j["id"] not in estado.get("transferibles", [])]
    respuesta = interrupt({"tipo": "elegir_transferible", "dia": estado["dia"],
                           "jugadores": [{k: j[k] for k in ("nombre", "posicion", "edad", "rating", "valor_mercado")}
                                         for j in candidatos]})
    texto = str(respuesta).strip().lower()
    if texto.isdigit() and 1 <= int(texto) <= len(candidatos):
        jugador = candidatos[int(texto) - 1]
        emitir("info", f"{jugador['nombre']} queda a la venta. Las ofertas llegarán a tu bandeja "
                       "(más probables en los primeros días del mercado).")
        return {"siguiente": "centro_de_mando", "transferibles": estado.get("transferibles", []) + [jugador["id"]]}
    if texto not in ("", "volver"):
        emitir("aviso", "No reconocí ese número.")
    return {"siguiente": "centro_de_mando"}


def turno_venta(estado):
    """Pausa: aceptar la oferta, rechazarla o pedir otras condiciones (en lenguaje natural)."""
    o = estado["ofertas_venta"][estado["oferta_activa"]]
    respuesta = interrupt({
        "tipo": "negociacion_venta", "jugador": o["jugador"]["nombre"], "club": o["club_comprador"],
        "oferta": describir_oferta(o["oferta"]), "ronda": o["ronda"] + 1, "max_rondas": MAX_RONDAS_VENTA,
        "valor_mercado": o["jugador"]["valor_mercado"],
        "ultimo_mensaje": o["historial"][-1]["texto"] if o["historial"] else "",
    })
    return {"texto_usuario": str(respuesta).strip()}


def interpretar_venta(estado):
    o = estado["ofertas_venta"][estado["oferta_activa"]]
    texto = estado["texto_usuario"]
    minuscula = texto.lower()
    if minuscula in ("aceptar", "acepto", "aceptamos"):
        return {"siguiente": "cerrar_venta", "resultado_negociacion": "acuerdo",
                "interpretacion": {"intencion": "aceptar_condiciones", "oferta": o["oferta"]}}
    if minuscula in ("rechazar", "rechazo", "rechazamos"):
        return {"siguiente": "cerrar_venta", "resultado_negociacion": "rechazo"}
    if not texto:
        return {"siguiente": "turno_venta"}
    inter = interprete.interpretar(texto, "ronda", describir_oferta(o["oferta"]))
    if inter["intencion"] == "aceptar_condiciones" and inter["ambigua"]:
        emitir("aviso", f"No queda claro si aceptas: {inter['duda']} Para cerrar escribe 'aceptar'; "
                        "si quieres pedir otra cifra, escríbela como oferta.")
        return {"siguiente": "turno_venta"}    
    if inter["intencion"] == "aceptar_condiciones":
        inter["oferta"] = normalizar_oferta(o["oferta"])
        return {"siguiente": "cerrar_venta", "resultado_negociacion": "acuerdo", "interpretacion": inter}
    if inter["intencion"] == "retirarse":
        return {"siguiente": "cerrar_venta", "resultado_negociacion": "rechazo"}
    if inter["intencion"] != "oferta":
        emitir("aviso", "Escribe cuánto pides (por ejemplo, '35 millones y un 10 % de una futura venta'), "
                        "'aceptar' o 'rechazar'.")
        return {"siguiente": "turno_venta"}
    ref = o["perfil"]["valor_referencia"]
    if valor_efectivo(inter["oferta"], ref) < valor_efectivo(o["oferta"], ref) - 0.01:
        inter["ambigua"] = True
        inter["duda"] = (f"pides {valor_efectivo(inter['oferta'], ref)} M€, menos de lo que ya te ofrecen "
                         f"({valor_efectivo(o['oferta'], ref)} M€). Aceptar su oferta te conviene más.")
    emitir("interpretacion", inter["resumen"] or describir_oferta(inter["oferta"]), oferta=inter["oferta"])
    return {"siguiente": "confirmar_interpretacion" if inter["ambigua"] else "responder_comprador",
            "interpretacion": inter}


def responder_comprador(estado):
    """El agente de club (rol comprador) decide; el código arbitra; se redacta si hubo corrección."""
    o = dict(estado["ofertas_venta"][estado["oferta_activa"]])
    perfil, j = o["perfil"], o["jugador"]
    pedido = normalizar_oferta(estado["interpretacion"]["oferta"])
    o["ronda"] += 1
    o["pedido"] = pedido
    o["historial"] = o["historial"] + [{"de": "vendedor", "texto": estado["texto_usuario"], "oferta": pedido}]

    propuesta = None
    if es_ridiculo(pedido, perfil):
        final, correcciones = {"accion": "rechazar", "contraoferta": None}, ["pedido muy por encima de lo razonable"]
    else:
        contexto = {
            "club_comprador": o["club_comprador"], "club_vendedor": estado["club"],
            "rondas_restantes": MAX_RONDAS_VENTA - o["ronda"] + 1,
            "jugador": {"nombre": j["nombre"], **{k: j[k] for k in ("edad", "posicion", "rating", "anios_contrato")},
                        "valor_mercado": perfil["valor_referencia"]},
            "tus_limites_SECRETOS": {"precio_maximo": perfil["precio_maximo"]},
            "lo_que_pide_el_vendedor": {**pedido, "descripcion": describir_oferta(pedido),
                                        "valor_para_ti_hoy": valor_efectivo(pedido, perfil["valor_referencia"])},
            "tu_ultima_oferta": {**o["oferta"], "descripcion": describir_oferta(o["oferta"])},
            "historial": [f"{h['de']}: {h['texto']}" for h in o["historial"][-6:]],
        }
        propuesta = club_vendedor.decidir_compra(contexto)
        final, correcciones = arbitrar_compra(propuesta, pedido, perfil, o["ronda"], o["oferta"])

    cifras_ok = [final["contraoferta"]["fijo"]] if final["contraoferta"] else [pedido["fijo"]]
    mensaje = (propuesta or {}).get("mensaje") if not correcciones else None
    if mensaje and revela_maximo(mensaje, perfil, cifras_ok):
        correcciones.append("el mensaje revelaba el precio máximo")
        mensaje = None
    if not mensaje:
        cifras = {"lo_que_piden": describir_oferta(pedido)}
        if final["contraoferta"]:
            cifras["nueva_oferta"] = describir_oferta(final["contraoferta"])
        decision = {"aceptar": "aceptas lo que pide el club vendedor", "rechazar": "te retiras de la negociación",
                    "contraofertar": "mejoras tu oferta"}[final["accion"]]
        mensaje = club_vendedor.redactar_compra(o["club_comprador"], j["nombre"], decision, cifras)
        if not mensaje or revela_maximo(mensaje, perfil, cifras_ok):
            mensaje = {"aceptar": "Aceptamos sus condiciones. Tenemos un acuerdo.",
                       "rechazar": "No podemos llegar a esas cifras. Nos retiramos.",
                       "contraofertar": f"Podemos mejorar: {cifras.get('nueva_oferta')}."}[final["accion"]]
    for c in correcciones:
        emitir("correccion_arbitro", c, agente="club_comprador", ronda=o["ronda"])
    o["historial"] = o["historial"] + [{"de": "comprador", "texto": mensaje, "oferta": final["contraoferta"]}]
    emitir("mensaje_club", mensaje, club=o["club_comprador"], rol="comprador", accion=final["accion"],
           contraoferta=describir_oferta(final["contraoferta"]) if final["contraoferta"] else "",
           decision_modelo=(propuesta or {}).get("accion"), correcciones=correcciones)

    cambios = {"ofertas_venta": _guardar(estado, o)}
    if final["accion"] == "contraofertar":
        o["oferta"] = final["contraoferta"]
        return {**cambios, "ofertas_venta": _guardar(estado, o), "siguiente": "turno_venta"}
    if final["accion"] == "aceptar":
        return {**cambios, "siguiente": "cerrar_venta", "resultado_negociacion": "acuerdo",
                "interpretacion": {"intencion": "oferta", "oferta": pedido}}
    return {**cambios, "siguiente": "cerrar_venta", "resultado_negociacion": "retiro_comprador"}


def cerrar_venta(estado):
    """Con acuerdo: el jugador se va, entra el dinero y baja la masa salarial. Sin acuerdo: la oferta se cierra."""
    o = dict(estado["ofertas_venta"][estado["oferta_activa"]])
    j, club = o["jugador"], estado["club"]
    resultado = estado.get("resultado_negociacion")
    ofertas = dict(estado.get("ofertas_venta", {}))
    cambios = {}
    if resultado == "acuerdo":
        acuerdo = normalizar_oferta(estado["interpretacion"]["oferta"])
        pago = primer_pago(acuerdo)
        registrar_traspaso(j["id"], o["club_comprador"], j["salario_anual"], j["anios_contrato"], j["titular"])
        ajustar_presupuesto(club, pago)
        ajustar_presupuesto(o["club_comprador"], -pago)
        o["fase"] = "vendida"
        for clave, otra in ofertas.items():   # las demás ofertas por el mismo jugador quedan sin efecto
            if otra["jugador"]["id"] == j["id"] and clave != o["id"]:
                ofertas[clave] = {**otra, "fase": "sin_efecto"}
        ingresos = [{"jugador": j["nombre"], "temporada": t, "monto": round(acuerdo["fijo"] / acuerdo["cuotas"], 2)}
                    for t in range(1, acuerdo["cuotas"])]
        desempeno = desempeno_venta(o["perfil"], acuerdo)
        venta = {"id": j["id"], "nombre": j["nombre"], "posicion": j["posicion"], "club_destino": o["club_comprador"],
                 "traspaso": describir_oferta(acuerdo), "ingreso_esta_ventana": pago, "desempeno": desempeno,
                 "dia": estado["dia"]}
        cambios = {"ventas": estado.get("ventas", []) + [venta],
                   "ingresos_futuros": estado.get("ingresos_futuros", []) + ingresos,
                   "transferibles": [t for t in estado.get("transferibles", []) if t != j["id"]],
                   "resumen": obtener_resumen_club(club), "plantilla": obtener_plantilla(club),
                   "diagnostico_vigente": False}
        emitir("venta", f"{j['nombre']} vendido a {o['club_comprador']}", **venta)
    else:
        o["fase"] = "rechazada" if resultado == "rechazo" else "retirada"
        emitir("info", f"Oferta de {o['club_comprador']} por {j['nombre']} cerrada sin acuerdo.")
    ofertas[o["id"]] = o
    cambios["ofertas_venta"] = ofertas
    if o["ronda"] == 0:   # se aceptó o rechazó sin negociar: no consume días
        return {**cambios, "siguiente": "centro_de_mando"}
    avance, cerrada = pasar_dias({**estado, **cambios}, DIAS_POR_NEGOCIACION)
    return {**cambios, **avance, "siguiente": "resumen_ventana" if cerrada else "centro_de_mando"}