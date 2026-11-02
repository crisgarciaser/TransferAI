"""Nodos del grafo para la negociación con el jugador y el cierre del fichaje (Paso 15).

Flujo (después del acuerdo con el club, desde el menú de fichajes y dentro del plazo):
  entrar_negociacion_jugador -> turno_jugador -> interpretar_turno_jugador
     -> dar_consejo_jugador | [confirmar_interpretacion] | responder_agente_jugador ... -> cerrar_fichaje
Una vez dentro no se vuelve al menú hasta el acuerdo o la ruptura.
Agentes: Player Agent (decide y redacta), Manager y Financial (consejo).
"""
from langgraph.types import interrupt

from agentes import agente_jugador, financiero, manager
from config import DIAS_POR_NEGOCIACION, MAX_RONDAS_JUGADOR
from datos import ajustar_presupuesto, cargar_clubes, intervalo_salario, obtener_plantilla, obtener_resumen_club, \
    registrar_traspaso
from negociacion import interprete
from negociacion.nodos_club import _activa, _guardar, _pedido_de_consejo, pasar_dias
from negociacion.reglas import describir_oferta, normalizar_oferta, primer_pago, valor_presente
from negociacion.reglas_jugador import (
    arbitrar_jugador, bonos_poco_probables, costo_anual_club, decision_respaldo, desempeno_jugador,
    describir_oferta_jugador, es_ridicula_jugador, normalizar_oferta_jugador, perfil_jugador, peticion_inicial,
    revela_privado, valor_anual_para_jugador,
)
from registro import emitir


def _clubes():
    return {c["club"]: c for c in cargar_clubes()}


def entrar_negociacion_jugador(estado):
    """Calcula la exigencia privada del jugador y su agente presenta la exigencia inicial."""
    reg = dict(_activa(estado))
    j = reg["jugador"]
    clubes = _clubes()
    sera_titular = j.get("tipo_de_fichaje") == "mejora_inmediata"
    perfil = perfil_jugador(j, clubes[reg["club_vendedor"]], clubes[estado["club"]], sera_titular)
    peticion = peticion_inicial(perfil)
    reg.update({"perfil_jugador": perfil, "ronda_jugador": 0, "peticion_jugador": peticion,
                "oferta_jugador": None, "historial_jugador": []})
    mensaje = agente_jugador.redactar(
        j.get("agencia"), perfil["estrella"], j["nombre"], estado["club"],
        "presentas las condiciones que pide tu representado para firmar",
        {"exigencia": describir_oferta_jugador(peticion), "rol_esperado": "titular" if sera_titular else "rotación"})
    if not mensaje or revela_privado(mensaje, perfil, [peticion["salario"]]):
        mensaje = f"Para firmar, {j['nombre']} pide {describir_oferta_jugador(peticion)}."
    reg["historial_jugador"] = [{"de": "jugador", "texto": mensaje, "oferta": peticion}]
    minimo, maximo = intervalo_salario(j)
    emitir("negociacion", f"Negociación con el agente de {j['nombre']}"
           + (f" ({j['agencia']})" if j.get("agencia") else ""),
           exigencia=describir_oferta_jugador(peticion), ultimo_mensaje=mensaje,
           salario_estimado=f"{minimo}-{maximo}")
    return {"negociaciones": _guardar(estado, reg), "etapa": "jugador"}


def turno_jugador(estado):
    reg = _activa(estado)
    respuesta = interrupt({
        "tipo": "negociacion_jugador", "jugador": reg["jugador"]["nombre"],
        "ronda": reg["ronda_jugador"] + 1, "max_rondas": MAX_RONDAS_JUGADOR,
        "exigencia": describir_oferta_jugador(reg["peticion_jugador"]),
        "margen_salarial": estado["resumen"]["margen_salarial"],
        "presupuesto": estado["resumen"]["presupuesto_fichajes"],
        "salario_estimado": "{}-{}".format(*intervalo_salario(reg["jugador"])),
    })
    return {"texto_usuario": str(respuesta).strip()}


def _validar_contrato(estado, reg, oferta):
    pos = reg["jugador"]["posicion"]
    costo = costo_anual_club(oferta, pos)
    if costo > estado["resumen"]["margen_salarial"]:
        return (f"El costo anual ({costo} M€ entre salario y bonos esperados) supera tu margen salarial "
                f"({estado['resumen']['margen_salarial']} M€).")
    pago_ventana = primer_pago(reg["acuerdo"]) + oferta["prima"]
    if pago_ventana > estado["resumen"]["presupuesto_fichajes"]:
        return (f"El primer pago del traspaso más la prima ({round(pago_ventana, 2)} M€) supera tu presupuesto "
                f"({estado['resumen']['presupuesto_fichajes']} M€).")
    return None


def interpretar_turno_jugador(estado):
    reg = _activa(estado)
    texto = estado["texto_usuario"]
    if not texto:
        return {"siguiente": "turno_jugador"}
    consejo = _pedido_de_consejo(texto)
    if consejo in ("manager", "financiero"):
        return {"siguiente": "dar_consejo_jugador", "tipo_consejo": consejo}
    if consejo == "sin_especificar":
        emitir("aviso", "Escribe 'consejo m' para el Manager Agent o 'consejo f' para el Financial Agent.")
        return {"siguiente": "turno_jugador"}

    inter = interprete.interpretar_jugador(texto, describir_oferta_jugador(reg["peticion_jugador"]))
    if inter["intencion"] == "retirarse":
        return {"siguiente": "cerrar_fichaje", "resultado_negociacion": "retiro", "interpretacion": inter}
    if inter["intencion"] == "aceptar_condiciones":
        inter["oferta"] = normalizar_oferta_jugador(reg["peticion_jugador"])
    if inter["intencion"] == "otro":
        emitir("aviso", "No entendí una oferta concreta. Indica al menos salario por temporada y años de contrato.")
        return {"siguiente": "turno_jugador"}
    error = _validar_contrato(estado, reg, inter["oferta"])
    if error:
        emitir("aviso", error)
        return {"siguiente": "turno_jugador"}
    raros = bonos_poco_probables(inter["oferta"]["bonos"], reg["jugador"]["posicion"])
    if raros:
        emitir("aviso", f"Los bonos por {', '.join(r.replace('_', ' ') for r in raros)} casi no tienen valor "
                        f"para un {reg['jugador']['posicion']}: el jugador apenas los considerará.")
    emitir("interpretacion", inter["resumen"] or describir_oferta_jugador(inter["oferta"]),
           intencion=inter["intencion"], oferta=inter["oferta"])
    return {"siguiente": "confirmar_interpretacion" if inter["ambigua"] else "responder_agente_jugador",
            "interpretacion": inter}


def dar_consejo_jugador(estado):
    reg = _activa(estado)
    j = reg["jugador"]
    exigencia = reg["peticion_jugador"]
    if estado.get("tipo_consejo") == "manager":
        consejo = manager.aconsejar(estado["club"], j["nombre"], {
            "contexto": "negociación del contrato con el jugador (el traspaso ya está acordado con su club)",
            "tipo_de_fichaje": j.get("tipo_de_fichaje", ""), "justificacion_del_scout": j.get("justificacion", ""),
            "jugador": {k: j[k] for k in ("edad", "rating", "potencial", "posicion")},
            "exigencia_del_jugador": describir_oferta_jugador(exigencia),
            "rondas_restantes": MAX_RONDAS_JUGADOR - reg["ronda_jugador"]})
        if consejo:
            emitir("consejo", consejo, agente="manager")
    else:
        minimo, maximo = intervalo_salario(j)
        consejo = financiero.aconsejar_salario({
            "margen_salarial": estado["resumen"]["margen_salarial"],
            "exigencia_del_jugador": describir_oferta_jugador(exigencia),
            "costo_anual_exigencia": costo_anual_club(exigencia, j["posicion"]),
            "presupuesto_disponible_para_prima": round(estado["resumen"]["presupuesto_fichajes"]
                                                       - primer_pago(reg["acuerdo"]), 2),
            "salario_actual_estimado": f"{minimo}-{maximo}"})
        emitir("consejo", consejo, agente="financiero")
    return {"siguiente": "turno_jugador"}


def responder_agente_jugador(estado):
    reg = dict(_activa(estado))
    j, perfil = reg["jugador"], reg["perfil_jugador"]
    pos = perfil["posicion"]
    inter = estado["interpretacion"]
    oferta = normalizar_oferta_jugador(inter["oferta"])
    reg["ronda_jugador"] += 1
    reg["oferta_jugador"] = oferta
    reg["historial_jugador"] = reg["historial_jugador"] + [{"de": "club", "texto": estado["texto_usuario"], "oferta": oferta}]

    propuesta = None
    if inter["intencion"] == "aceptar_condiciones":
        final, correcciones = {"accion": "aceptar", "contraoferta": None}, []
    elif es_ridicula_jugador(oferta, perfil):
        final, correcciones = {"accion": "rechazar", "contraoferta": None}, ["oferta muy por debajo de lo razonable: ruptura inmediata"]
    else:
        contexto = {
            "agencia": j.get("agencia"), "estrella": perfil["estrella"], "club_comprador": estado["club"],
            "anios_preferidos": perfil["anios_preferidos"],
            "rondas_restantes": MAX_RONDAS_JUGADOR - reg["ronda_jugador"] + 1,
            "jugador": {"nombre": j["nombre"], **{k: j[k] for k in ("edad", "posicion", "rating", "potencial")},
                        "club_actual": reg["club_vendedor"]},
            "rol_en_el_nuevo_club": "titular" if perfil["sera_titular"] else "rotación",
            "tus_limites_SECRETOS": {"salario_actual": perfil["salario_actual"],
                                     "exigencia_minima_anual": perfil["salario_minimo"],
                                     "exigencia_inicial_anual": perfil["salario_pedido"]},
            "oferta_actual_del_club": {**oferta, "descripcion": describir_oferta_jugador(oferta),
                                       "valor_anual_para_tu_representado": valor_anual_para_jugador(oferta, pos)},
            "tu_ultima_exigencia": {**reg["peticion_jugador"],
                                    "valor_anual": valor_anual_para_jugador(reg["peticion_jugador"], pos)},
            "historial": [f"{h['de']}: {h['texto']}" for h in reg["historial_jugador"][-6:]],
        }
        propuesta = agente_jugador.decidir(contexto)
        final, correcciones = arbitrar_jugador(propuesta, oferta, perfil, reg["ronda_jugador"], reg["peticion_jugador"])

    cifras_ok = [final["contraoferta"]["salario"]] if final["contraoferta"] else [oferta["salario"]]
    mensaje = (propuesta or {}).get("mensaje") if not correcciones else None
    if mensaje and revela_privado(mensaje, perfil, cifras_ok):
        correcciones.append("el mensaje revelaba el salario actual o la exigencia mínima")
        mensaje = None
    if not mensaje:
        cifras = {"oferta_recibida": describir_oferta_jugador(oferta)}
        if final["contraoferta"]:
            cifras["nueva_exigencia"] = describir_oferta_jugador(final["contraoferta"])
        decision = {"aceptar": "aceptas la oferta", "rechazar": "rechazas la oferta y das por terminada la negociación",
                    "contraofertar": "haces una contraoferta"}[final["accion"]]
        mensaje = agente_jugador.redactar(j.get("agencia"), perfil["estrella"], j["nombre"], estado["club"], decision, cifras)
        if not mensaje or revela_privado(mensaje, perfil, cifras_ok):
            mensaje = {"aceptar": f"{j['nombre']} acepta las condiciones. Tenemos un acuerdo.",
                       "rechazar": f"Lo sentimos, {j['nombre']} no continuará esta negociación.",
                       "contraofertar": f"Aún no es suficiente. Pedimos: {cifras.get('nueva_exigencia')}."}[final["accion"]]
    for c in correcciones:
        emitir("correccion_arbitro", c, agente="agente_jugador", ronda=reg["ronda_jugador"], jugador_id=j["id"])

    reg["historial_jugador"] = reg["historial_jugador"] + [{"de": "jugador", "texto": mensaje, "oferta": final["contraoferta"]}]
    emitir("mensaje_club", mensaje, club=f"Agente de {j['nombre']}", accion=final["accion"],
           contraoferta=describir_oferta_jugador(final["contraoferta"]) if final["contraoferta"] else "",
           decision_modelo=(propuesta or {}).get("accion"), correcciones=correcciones,
           respaldo=decision_respaldo(oferta, perfil, reg["ronda_jugador"], reg["peticion_jugador"])["accion"])

    if final["accion"] == "contraofertar":
        reg["peticion_jugador"] = final["contraoferta"]
        return {"negociaciones": _guardar(estado, reg), "siguiente": "turno_jugador"}
    if final["accion"] == "aceptar":
        reg["contrato"] = oferta
        return {"negociaciones": _guardar(estado, reg), "siguiente": "cerrar_fichaje", "resultado_negociacion": "acuerdo"}
    return {"negociaciones": _guardar(estado, reg), "siguiente": "cerrar_fichaje", "resultado_negociacion": "ruptura"}


def cerrar_fichaje(estado):
    """Con acuerdo: el jugador pasa al club y se actualizan presupuesto, masa salarial y plantilla.
    Sin acuerdo: el acuerdo con el club se cae. En ambos casos se muestra el desempeño y pasa un día."""
    reg = dict(_activa(estado))
    j, perfil = reg["jugador"], reg["perfil_jugador"]
    club = estado["club"]
    cambios = {}
    if estado.get("resultado_negociacion") == "acuerdo":
        contrato = reg["contrato"]
        acuerdo = normalizar_oferta(reg["acuerdo"])
        pago_traspaso = primer_pago(acuerdo)
        registrar_traspaso(j["id"], club, contrato["salario"], contrato["anios"],
                           "si" if perfil["sera_titular"] else "no")
        ajustar_presupuesto(club, -(pago_traspaso + contrato["prima"]))
        ajustar_presupuesto(reg["club_vendedor"], pago_traspaso)
        compromisos = [{"jugador": j["nombre"], "temporada": t, "monto": round(acuerdo["fijo"] / acuerdo["cuotas"], 2)}
                       for t in range(1, acuerdo["cuotas"])]
        reg["fase"] = "cerrada"
        reg["desempeno_jugador"] = desempeno_jugador(perfil, acuerdo=contrato)
        fichaje = {"id": j["id"], "nombre": j["nombre"], "posicion": j["posicion"], "club_origen": reg["club_vendedor"],
                   "traspaso": describir_oferta(acuerdo), "contrato": describir_oferta_jugador(contrato),
                   "pago_esta_ventana": round(pago_traspaso + contrato["prima"], 2),
                   "desempeno_club": reg["desempeno"], "desempeno_jugador": reg["desempeno_jugador"], "dia": estado["dia"]}
        cambios = {"fichajes": estado.get("fichajes", []) + [fichaje],
                   "objetivos": [o for o in estado.get("objetivos", []) if o["id"] != j["id"]],
                   "compromisos": estado.get("compromisos", []) + compromisos,
                   "resumen": obtener_resumen_club(club), "plantilla": obtener_plantilla(club)}
        emitir("fichaje", f"¡{j['nombre']} es nuevo jugador de {club}!", **fichaje)
    else:
        reg["fase"] = "fracasada"
        reg["desempeno_jugador"] = desempeno_jugador(perfil, ultima_oferta=reg.get("oferta_jugador"))
        if estado.get("resultado_negociacion") == "retiro":
            emitir("info", f"Te retiraste de la negociación con {j['nombre']}. El acuerdo con {reg['club_vendedor']} se cae.")
        else:
            emitir("info", f"No hubo acuerdo con {j['nombre']}. El acuerdo con {reg['club_vendedor']} se cae.")
    emitir("desempeno_jugador", f"Negociación con {j['nombre']}", jugador=j["nombre"], **reg["desempeno_jugador"])
    estado_parcial = {**estado, **cambios, "negociaciones": _guardar(estado, reg)}
    avance, cerrada = pasar_dias(estado_parcial, DIAS_POR_NEGOCIACION)
    return {**cambios, **avance, "siguiente": "resumen_ventana" if cerrada else "centro_de_mando"}
