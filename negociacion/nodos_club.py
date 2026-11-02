"""Nodos del grafo para la negociación con el club vendedor (Paso 14).

Flujo:
  centro de mando -> menu_fichajes
    -> (objetivo sin oferta)  escribir_primer_contacto -> interpretar_primer_contacto
         -> [confirmar_interpretacion] -> enviar_primer_contacto -> centro de mando
         (la respuesta del club llega días después a la bandeja, ver pasar_dias)
Agentes que participan: Selling Club Agent (decide y redacta), Manager y Financial (consejo).
La herramienta de interpretación (negociacion/interprete.py) traduce los mensajes del usuario.
    -> (negociación abierta)  entrar_negociacion -> turno_comprador -> interpretar_turno
         -> dar_consejo | [confirmar_interpretacion] | responder_vendedor ... -> cerrar_negociacion_club
Una vez dentro de una negociación abierta no se vuelve al menú hasta el acuerdo o la ruptura.

Regla de LangGraph: un nodo con interrupt() se ejecuta de nuevo desde el inicio al reanudarse;
por eso las llamadas al modelo están siempre en nodos distintos de las pausas.
"""
from langgraph.types import interrupt

from agentes import club_vendedor, financiero, manager
from negociacion import interprete
from config import DIAS_PLAZO_JUGADOR, DIAS_POR_NEGOCIACION, DIAS_VENTANA, MAX_RONDAS_CLUB
from datos import cargar_clubes, obtener_plantilla
from negociacion.reglas import (
    arbitrar, decision_respaldo, describir_oferta, desempeno, es_ridicula, evaluar_oferta_inicial,
    normalizar_oferta, oferta_de_pedido, perfil_vendedor, primer_pago, revela_minimo, valor_efectivo,
)
from registro import emitir
from ventana import avanzar, programar

ESTADOS_LEGIBLES = {
    "sin_oferta": "sin oferta", "esperando": "esperando respuesta", "abierta": "negociación abierta",
    "acuerdo_club": "acuerdo con el club: falta negociar con el jugador", "fracasada": "negociación rota",
    "cerrada": "fichaje cerrado",
    "bloqueado": "bloqueado (rechazó dos ofertas)",
}


# ======================================================================
# UTILIDADES
# ======================================================================
def _clubes():
    return {c["club"]: c for c in cargar_clubes()}


def _registro(estado, jugador):
    """Devuelve la negociación de un jugador (la crea si no existe)."""
    negociaciones = estado.get("negociaciones", {})
    clave = str(jugador["id"])
    if clave in negociaciones:
        return negociaciones[clave]
    clubes = _clubes()
    perfil = perfil_vendedor(jugador, obtener_plantilla(jugador["club"]),
                             clubes[jugador["club"]], clubes[estado["club"]])
    return {"jugador": jugador, "club_vendedor": jugador["club"], "fase": "sin_oferta", "intentos": 0,
            "perfil": perfil, "historial": [], "ronda": 0, "ultima_peticion": None,
            "ultima_oferta": None, "acuerdo": None, "desempeno": None}


def _guardar(estado, registro):
    return {**estado.get("negociaciones", {}), str(registro["jugador"]["id"]): registro}


def _activa(estado):
    return estado["negociaciones"][estado["negociacion_activa"]]


def pasar_dias(estado, dias):
    """Avanza el tiempo y aplica a las negociaciones las respuestas que llegan.

    Devuelve (cambios_de_estado, ventana_cerrada). La usan avanzar_dias (centro de mando) y el
    cierre de cada negociación (que consume DIAS_POR_NEGOCIACION días).
    """
    dia, calendario, bandeja, llegados, cerrada = avanzar(
        estado["dia"], dias, estado.get("calendario", []), estado.get("bandeja", []))
    negociaciones = dict(estado.get("negociaciones", {}))
    emitir("dia", f"Día {dia} de {DIAS_VENTANA}", dia=dia)
    for evento in llegados:
        emitir("mensaje", evento["asunto"], dia=evento["dia"], tipo_mensaje=evento["tipo"])
        if evento["tipo"] == "respuesta_primer_contacto":
            clave = str(evento["datos"]["jugador_id"])
            if clave in negociaciones:
                negociaciones[clave] = aplicar_respuesta(negociaciones[clave], evento)
    # Plazo para empezar a negociar con el jugador después del acuerdo con su club
    for clave, reg in negociaciones.items():
        if reg["fase"] == "acuerdo_club" and dia > reg.get("dia_acuerdo", dia) + DIAS_PLAZO_JUGADOR:
            nombre = reg["jugador"]["nombre"]
            negociaciones[clave] = {**reg, "fase": "fracasada"}
            texto = (f"Pasaron más de {DIAS_PLAZO_JUGADOR} días sin noticias de su club. {nombre} decidió "
                     "seguir otro camino y rechaza definitivamente la operación.")
            bandeja = bandeja + [{"id": 10_000 + len(bandeja), "dia": dia, "tipo": "plazo_vencido",
                                  "asunto": f"El agente de {nombre} cierra la puerta", "datos": {"mensaje": texto},
                                  "leido": False}]
            emitir("mensaje", f"El agente de {nombre} cierra la puerta (venció el plazo)", dia=dia)
    if cerrada:
        emitir("aviso", f"Se cumplieron los {DIAS_VENTANA} días: el mercado de fichajes se cierra.")
    return {"dia": dia, "calendario": calendario, "bandeja": bandeja, "negociaciones": negociaciones}, cerrada


def aplicar_respuesta(registro, evento):
    """Actualiza la negociación cuando llega la respuesta del club al primer contacto."""
    d = evento["datos"]
    r = {**registro, "historial": registro["historial"] + [
        {"de": "vendedor", "texto": d["mensaje"], "oferta": d.get("peticion"), "dia": evento["dia"]}]}
    if d["resultado"] == "abre":
        r["fase"], r["ultima_peticion"] = "abierta", d["peticion"]
    elif d["resultado"] in ("acepta", "acepta_clausula"):
        r["fase"], r["acuerdo"], r["dia_acuerdo"] = "acuerdo_club", d["oferta"], evento["dia"]
        r["desempeno"] = desempeno(r["perfil"], precio_acordado=d["oferta"])
    elif d["resultado"] == "rechaza" and r["intentos"] >= 2:
        r["fase"] = "bloqueado"
    else:  # rechaza (primer intento) o solo_clausula: se puede volver a intentar
        r["fase"] = "sin_oferta"
    return r


# ======================================================================
# MENÚ DE FICHAJES
# ======================================================================
def menu_fichajes(estado):
    """Pausa: el usuario elige a qué objetivo ofertar o qué negociación abierta continuar."""
    filas = []
    for o in estado.get("objetivos", []):
        reg = estado.get("negociaciones", {}).get(str(o["id"]))
        fase = reg["fase"] if reg else "sin_oferta"
        intentos = reg["intentos"] if reg else 0
        texto = ESTADOS_LEGIBLES[fase] + (f" ({intentos}/2 ofertas)" if intentos and fase in ("sin_oferta", "esperando") else "")
        if fase == "acuerdo_club":
            texto += f" (plazo hasta el día {reg.get('dia_acuerdo', estado['dia']) + DIAS_PLAZO_JUGADOR})"
        filas.append({"id": o["id"], "nombre": o["nombre"], "club": o["club"], "posicion": o["posicion"],
                      "fase": fase, "estado": texto})
    respuesta = interrupt({"tipo": "menu_fichajes", "objetivos": filas, "dia": estado["dia"]})

    texto = str(respuesta).strip().lower()
    if texto in ("", "volver", "salir", "0"):
        return {"siguiente": "centro_de_mando"}
    elegido = None
    if texto.isdigit():
        n = int(texto)
        elegido = next((f for f in filas if f["id"] == n), None)
        if elegido is None and 1 <= n <= len(filas):
            elegido = filas[n - 1]  # también acepta el número de la lista
    if elegido is None:
        emitir("aviso", "No reconocí ese objetivo. Escribe su número de la lista o 'volver'.")
        return {"siguiente": "menu_fichajes"}
    if elegido["fase"] == "sin_oferta":
        jugador = next(o for o in estado["objetivos"] if o["id"] == elegido["id"])
        registro = _registro(estado, jugador)
        return {"siguiente": "escribir_primer_contacto", "negociacion_activa": str(jugador["id"]),
                "negociaciones": _guardar(estado, registro)}
    if elegido["fase"] == "abierta":
        return {"siguiente": "entrar_negociacion", "negociacion_activa": str(elegido["id"])}
    if elegido["fase"] == "acuerdo_club":
        return {"siguiente": "entrar_negociacion_jugador", "negociacion_activa": str(elegido["id"])}
    emitir("aviso", f"{elegido['nombre']}: {elegido['estado']}. No hay nada que hacer por ahora.")
    return {"siguiente": "centro_de_mando"}


# ======================================================================
# PRIMER CONTACTO
# ======================================================================
def escribir_primer_contacto(estado):
    """Pausa: el usuario escribe su primer mensaje al club vendedor."""
    reg = _activa(estado)
    j = reg["jugador"]
    respuesta = interrupt({
        "tipo": "primer_contacto", "jugador": j["nombre"], "club_vendedor": reg["club_vendedor"],
        "intento": reg["intentos"] + 1, "valor_mercado": j["valor_mercado"],
        "clausula": reg["perfil"]["clausula"], "presupuesto": estado["resumen"]["presupuesto_fichajes"],
    })
    texto = str(respuesta).strip()
    if texto.lower() in ("", "volver"):
        return {"siguiente": "centro_de_mando", "texto_usuario": ""}
    return {"siguiente": "interpretar_primer_contacto", "texto_usuario": texto, "etapa": "primer_contacto"}


def _validar_oferta(estado, reg, interpretacion):
    """Reglas del código sobre la oferta del usuario. Devuelve un texto de error o None."""
    oferta = interpretacion["oferta"]
    if interpretacion["intencion"] == "clausula":
        if not reg["perfil"]["clausula"]:
            return "Este jugador no tiene cláusula de rescisión."
        oferta["fijo"] = reg["perfil"]["clausula"]
    presupuesto = estado["resumen"]["presupuesto_fichajes"]
    if interpretacion["intencion"] in ("oferta", "clausula", "aceptar_condiciones") and primer_pago(oferta) > presupuesto:
        return (f"El pago de esta ventana ({primer_pago(oferta)} M€) supera tu presupuesto ({presupuesto} M€). "
                "Puedes bajar la cifra o repartirla en cuotas.")
    return None


def interpretar_primer_contacto(estado):
    """El agente intérprete convierte el mensaje en intención y oferta; el código valida."""
    reg = _activa(estado)
    inter = interprete.interpretar(estado["texto_usuario"], "primer_contacto")
    if inter["intencion"] not in ("interes", "oferta", "clausula"):
        emitir("aviso", "Para el primer contacto escribe un mensaje de interés, una oferta o el pago de la cláusula.")
        return {"siguiente": "escribir_primer_contacto"}
    error = _validar_oferta(estado, reg, inter)
    if error:
        emitir("aviso", error)
        return {"siguiente": "escribir_primer_contacto"}
    emitir("interpretacion", inter["resumen"] or describir_oferta(inter["oferta"]),
           intencion=inter["intencion"], oferta=inter["oferta"])
    siguiente = "confirmar_interpretacion" if inter["ambigua"] else "enviar_primer_contacto"
    return {"siguiente": siguiente, "interpretacion": inter}


def confirmar_interpretacion(estado):
    """Pausa (solo si el mensaje era ambiguo): el usuario confirma lo que entendió el intérprete."""
    inter = estado["interpretacion"]
    if estado["etapa"] == "jugador":
        from negociacion.reglas_jugador import describir_oferta_jugador
        texto_oferta = describir_oferta_jugador(inter["oferta"])
    else:
        texto_oferta = describir_oferta(inter["oferta"])
    respuesta = interrupt({"tipo": "confirmar_interpretacion", "resumen": inter["resumen"],
                           "duda": inter["duda"], "oferta": texto_oferta})
    ok = str(respuesta).strip().lower() in ("s", "si", "sí", "y")
    if estado["etapa"] == "primer_contacto":
        return {"siguiente": "enviar_primer_contacto" if ok else "escribir_primer_contacto"}
    if estado["etapa"] == "jugador":
        return {"siguiente": "responder_agente_jugador" if ok else "turno_jugador"}
    return {"siguiente": "responder_vendedor" if ok else "turno_comprador"}


def _mensaje_respuesta_inicial(reg, evaluacion, oferta, peticion):
    """Texto de la respuesta del club al primer contacto (redactado por el agente; plantilla si falla)."""
    perfil, j = reg["perfil"], reg["jugador"]
    cifras = {"jugador": j["nombre"], "decision": evaluacion["resultado"], "motivo": evaluacion["motivo"]}
    if peticion:
        cifras["nuestra_exigencia"] = describir_oferta(peticion)
    if evaluacion["resultado"] == "solo_clausula":
        cifras["clausula"] = perfil["clausula"]
    if oferta:
        cifras["oferta_recibida"] = describir_oferta(oferta)
    decision = {"abre": "aceptas iniciar negociaciones y comunicas tu exigencia inicial",
                "rechaza": "rechazas la oferta por insuficiente",
                "solo_clausula": "el jugador no está en venta; solo saldría si pagan su cláusula",
                "acepta": "aceptas la oferta tal como viene",
                "acepta_clausula": "confirmas que recibirán el pago de la cláusula y autorizas a hablar con el jugador",
                }[evaluacion["resultado"]]
    texto = club_vendedor.redactar(reg["club_vendedor"], j["nombre"], decision, cifras)
    if texto and not revela_minimo(texto, perfil, [peticion["fijo"]] if peticion else []):
        return texto
    plantillas = {
        "abre": f"Estamos dispuestos a escuchar. Nuestra exigencia por {j['nombre']} es: {cifras.get('nuestra_exigencia')}.",
        "rechaza": f"Agradecemos el interés, pero la oferta por {j['nombre']} no se ajusta a su valor.",
        "solo_clausula": f"{j['nombre']} no está en venta. Solo saldría con el pago de su cláusula ({perfil['clausula']} M€).",
        "acepta": f"Aceptamos su oferta por {j['nombre']}.",
        "acepta_clausula": f"Recibiremos el pago de la cláusula de {j['nombre']}. Pueden hablar con el jugador.",
    }
    return plantillas[evaluacion["resultado"]]


def enviar_primer_contacto(estado):
    """El código decide la respuesta del club y cuándo llega; el agente la redacta."""
    reg = dict(_activa(estado))
    inter = estado["interpretacion"]
    oferta = inter["oferta"] if inter["intencion"] in ("oferta", "clausula") else None
    if inter["intencion"] == "clausula":
        oferta = normalizar_oferta({"fijo": reg["perfil"]["clausula"], "clausula": True})

    evaluacion = evaluar_oferta_inicial(inter["intencion"], oferta, reg["perfil"])
    if (evaluacion["resultado"] == "abre" and oferta
            and valor_efectivo(oferta, reg["perfil"]["valor_referencia"]) >= reg["perfil"]["precio_pedido"]):
        evaluacion["resultado"] = "acepta"  # la primera oferta ya cubre lo que pedía el club
    peticion = oferta_de_pedido(reg["perfil"]) if evaluacion["resultado"] == "abre" else None
    mensaje = _mensaje_respuesta_inicial(reg, evaluacion, oferta, peticion)

    if oferta:
        reg["intentos"] += 1
        reg["ultima_oferta"] = oferta
    reg["fase"] = "esperando"
    reg["historial"] = reg["historial"] + [{"de": "comprador", "texto": estado["texto_usuario"], "oferta": oferta,
                                            "dia": estado["dia"]}]
    calendario = programar(estado.get("calendario", []), estado["dia"], evaluacion["dias"],
                           "respuesta_primer_contacto",
                           f"{reg['club_vendedor']} responde sobre {reg['jugador']['nombre']}",
                           {"jugador_id": reg["jugador"]["id"], "resultado": evaluacion["resultado"],
                            "mensaje": mensaje, "peticion": peticion, "oferta": oferta})
    emitir("info", f"Mensaje enviado a {reg['club_vendedor']}. La respuesta llegará en "
                   f"{evaluacion['dias']} día(s) (día {estado['dia'] + evaluacion['dias']}).",
           jugador_id=reg["jugador"]["id"], resultado_privado=evaluacion["resultado"])
    return {"siguiente": "centro_de_mando", "negociaciones": _guardar(estado, reg), "calendario": calendario}


# ======================================================================
# RONDAS DE NEGOCIACIÓN
# ======================================================================
def entrar_negociacion(estado):
    reg = _activa(estado)
    ultimo = next((h for h in reversed(reg["historial"]) if h["de"] == "vendedor"), None)
    emitir("negociacion", f"Negociación con {reg['club_vendedor']} por {reg['jugador']['nombre']}",
           exigencia=describir_oferta(reg["ultima_peticion"]), ultimo_mensaje=ultimo["texto"] if ultimo else "")
    return {"etapa": "ronda"}


def turno_comprador(estado):
    """Pausa: el usuario escribe su oferta, acepta, pide consejo o se retira."""
    reg = _activa(estado)
    respuesta = interrupt({
        "tipo": "negociacion_club", "jugador": reg["jugador"]["nombre"], "club_vendedor": reg["club_vendedor"],
        "ronda": reg["ronda"] + 1, "max_rondas": MAX_RONDAS_CLUB,
        "exigencia": describir_oferta(reg["ultima_peticion"]),
        "presupuesto": estado["resumen"]["presupuesto_fichajes"], "valor_mercado": reg["jugador"]["valor_mercado"],
    })
    return {"texto_usuario": str(respuesta).strip()}


def _pedido_de_consejo(texto):
    """Detecta 'consejo m' / 'consejo f' sin gastar una llamada al modelo.
    Devuelve "manager", "financiero", "sin_especificar" o None (no es un pedido de consejo)."""
    partes = texto.strip().lower().split()
    if not partes or partes[0] != "consejo":
        return None
    if len(partes) == 1:
        return "sin_especificar"
    if partes[1] in ("m", "manager"):
        return "manager"
    if partes[1] in ("f", "financiero", "financial"):
        return "financiero"
    return "sin_especificar"


def interpretar_turno(estado):
    reg = _activa(estado)
    if not estado["texto_usuario"]:
        return {"siguiente": "turno_comprador"}
    consejo = _pedido_de_consejo(estado["texto_usuario"])
    if consejo in ("manager", "financiero"):
        return {"siguiente": "dar_consejo", "tipo_consejo": consejo}
    if consejo == "sin_especificar":
        emitir("aviso", "Escribe 'consejo m' para el Manager Agent o 'consejo f' para el Financial Agent.")
        return {"siguiente": "turno_comprador"}
    inter = interprete.interpretar(estado["texto_usuario"], "ronda", describir_oferta(reg["ultima_peticion"]))
    i = inter["intencion"]
    if i == "consejo":
        emitir("aviso", "Si quieres consejo, escribe 'consejo m' (Manager Agent) o 'consejo f' (Financial Agent).")
        return {"siguiente": "turno_comprador"}
    if i == "retirarse":
        return {"siguiente": "cerrar_negociacion_club", "interpretacion": inter, "resultado_negociacion": "retiro"}
    if i == "aceptar_condiciones":
        inter["oferta"] = normalizar_oferta(reg["ultima_peticion"])
    if i in ("otro", "interes"):
        emitir("aviso", "No entendí una oferta concreta. Escribe cifras, acepta sus condiciones, pide 'consejo' o retírate.")
        return {"siguiente": "turno_comprador"}
    error = _validar_oferta(estado, reg, inter)
    if error:
        emitir("aviso", error)
        return {"siguiente": "turno_comprador"}
    if i == "clausula":
        inter["oferta"] = normalizar_oferta({"fijo": reg["perfil"]["clausula"], "clausula": True})
    emitir("interpretacion", inter["resumen"] or describir_oferta(inter["oferta"]), intencion=i, oferta=inter["oferta"])
    return {"siguiente": "confirmar_interpretacion" if inter["ambigua"] else "responder_vendedor",
            "interpretacion": inter}


def dar_consejo(estado):
    """Consejo entre rondas: 'consejo m' (Manager Agent, lo deportivo) o 'consejo f' (Financial Agent,
    lo económico). Se piden por separado para no gastar dos llamadas cada vez.
    Ninguno conoce el precio mínimo del vendedor."""
    reg = _activa(estado)
    j = reg["jugador"]
    ultima_oferta = describir_oferta(reg["ultima_oferta"]) if reg["ultima_oferta"] else "ninguna"
    if estado.get("tipo_consejo") == "manager":
        deportivo = {
            "tipo_de_fichaje": j.get("tipo_de_fichaje", ""), "justificacion_del_scout": j.get("justificacion", ""),
            "jugador": {k: j[k] for k in ("edad", "rating", "potencial", "anios_contrato", "posicion")},
            "ultima_exigencia_vendedor": describir_oferta(reg["ultima_peticion"]),
            "ultima_oferta_propia": ultima_oferta, "rondas_restantes": MAX_RONDAS_CLUB - reg["ronda"],
        }
        consejo = manager.aconsejar(estado["club"], j["nombre"], deportivo)
        if consejo:
            emitir("consejo", consejo, agente="manager")
    else:
        consejo = financiero.aconsejar(
            reg["ultima_peticion"]["fijo"], estado["resumen"]["presupuesto_fichajes"],
            {"valor_mercado_estimado": j["valor_mercado"], "ultima_oferta_propia": ultima_oferta})
        emitir("consejo", consejo, agente="financiero")
    return {"siguiente": "turno_comprador"}


def responder_vendedor(estado):
    """El Selling Club Agent decide; el código arbitra; el agente redacta si hubo corrección."""
    reg = dict(_activa(estado))
    perfil, j = reg["perfil"], reg["jugador"]
    inter = estado["interpretacion"]
    oferta = normalizar_oferta(inter["oferta"])
    reg["ronda"] += 1
    reg["ultima_oferta"] = oferta
    reg["historial"] = reg["historial"] + [{"de": "comprador", "texto": estado["texto_usuario"], "oferta": oferta,
                                            "dia": estado["dia"]}]
    ref = perfil["valor_referencia"]

    # Casos que decide el código sin consultar al modelo
    if inter["intencion"] in ("clausula", "aceptar_condiciones"):
        final, correcciones, propuesta = {"accion": "aceptar", "contraoferta": None}, [], None
    elif es_ridicula(oferta, perfil):
        final, correcciones, propuesta = {"accion": "rechazar", "contraoferta": None}, ["oferta ridícula: ruptura inmediata"], None
    else:
        contexto = {
            "club_vendedor": reg["club_vendedor"], "rondas_restantes": MAX_RONDAS_CLUB - reg["ronda"] + 1,
            "jugador": {"nombre": j["nombre"], **{k: j[k] for k in ("edad", "posicion", "rating", "potencial",
                                                                    "anios_contrato", "titular")},
                        "es_el_mejor_de_su_posicion": perfil["es_mejor_de_su_posicion"], "valor_mercado": ref},
            "comprador": {"club": estado["club"], "nivel": estado["resumen"]["nivel"], "es_tu_rival": perfil["es_rival"]},
            "tus_limites_SECRETOS": {"precio_minimo": perfil["precio_minimo"], "precio_pedido": perfil["precio_pedido"]},
            "oferta_actual_del_comprador": {**oferta, "descripcion": describir_oferta(oferta),
                                            "valor_para_ti_hoy": valor_efectivo(oferta, ref)},
            "tu_ultima_exigencia": {**(reg["ultima_peticion"] or {}),
                                    "valor_para_ti_hoy": valor_efectivo(reg["ultima_peticion"], ref)},
            "ronda": reg["ronda"],
            "historial": [f"{h['de']}: {h['texto']}" for h in reg["historial"][-6:]],
        }
        propuesta = club_vendedor.decidir(contexto)
        final, correcciones = arbitrar(propuesta, oferta, perfil, reg["ronda"], reg["ultima_peticion"])

    # Mensaje: el del modelo si no hubo correcciones ni filtraciones; si no, se vuelve a redactar
    cifras_ok = [final["contraoferta"]["fijo"]] if final["contraoferta"] else []
    mensaje = (propuesta or {}).get("mensaje") if not correcciones else None
    if mensaje and revela_minimo(mensaje, perfil, cifras_ok):
        correcciones.append("el mensaje revelaba el precio mínimo")
        mensaje = None
    if not mensaje:
        cifras = {"oferta_recibida": describir_oferta(oferta)}
        if final["contraoferta"]:
            cifras["nueva_exigencia"] = describir_oferta(final["contraoferta"])
        texto_decision = {"aceptar": "aceptas la oferta", "rechazar": "rechazas la oferta y das por terminada la negociación",
                          "contraofertar": "haces una contraoferta"}[final["accion"]]
        mensaje = club_vendedor.redactar(reg["club_vendedor"], j["nombre"], texto_decision, cifras)
        if not mensaje or revela_minimo(mensaje, perfil, cifras_ok):
            mensaje = {"aceptar": f"Tenemos un acuerdo por {j['nombre']}.",
                       "rechazar": f"Lamentablemente no hay acuerdo posible por {j['nombre']}. Damos por cerrada la negociación.",
                       "contraofertar": f"No es suficiente. Nuestra posición ahora es: {cifras.get('nueva_exigencia')}."
                       }[final["accion"]]
    for c in correcciones:
        emitir("correccion_arbitro", c, agente="club_vendedor", ronda=reg["ronda"], jugador_id=j["id"])

    reg["historial"] = reg["historial"] + [{"de": "vendedor", "texto": mensaje, "oferta": final["contraoferta"],
                                            "dia": estado["dia"]}]
    emitir("mensaje_club", mensaje, club=reg["club_vendedor"], accion=final["accion"],
           contraoferta=describir_oferta(final["contraoferta"]) if final["contraoferta"] else "",
           decision_modelo=(propuesta or {}).get("accion"), correcciones=correcciones,
           respaldo=decision_respaldo(oferta, perfil, reg["ronda"], reg["ultima_peticion"])["accion"])

    if final["accion"] == "contraofertar":
        reg["ultima_peticion"] = final["contraoferta"]
        return {"negociaciones": _guardar(estado, reg), "siguiente": "turno_comprador"}
    if final["accion"] == "aceptar":
        reg["acuerdo"] = oferta
        return {"negociaciones": _guardar(estado, reg), "siguiente": "cerrar_negociacion_club",
                "resultado_negociacion": "acuerdo"}
    return {"negociaciones": _guardar(estado, reg), "siguiente": "cerrar_negociacion_club",
            "resultado_negociacion": "ruptura"}


def cerrar_negociacion_club(estado):
    """Cierra la negociación (acuerdo, ruptura o retiro), muestra el desempeño y consume un día."""
    reg = dict(_activa(estado))
    resultado = estado.get("resultado_negociacion")
    if resultado == "acuerdo":
        reg["fase"] = "acuerdo_club"
        reg["dia_acuerdo"] = estado["dia"]
        reg["desempeno"] = desempeno(reg["perfil"], precio_acordado=reg["acuerdo"])
    else:
        reg["fase"] = "fracasada"
        reg["desempeno"] = desempeno(reg["perfil"], ultima_oferta=reg["ultima_oferta"])
        if resultado == "retiro":
            emitir("info", f"Te retiraste de la negociación por {reg['jugador']['nombre']}.")
    emitir("desempeno", f"Resultado de la negociación por {reg['jugador']['nombre']}",
           jugador=reg["jugador"]["nombre"], acuerdo=describir_oferta(reg["acuerdo"]) if reg["acuerdo"] else "",
           **reg["desempeno"])
    estado_parcial = {**estado, "negociaciones": _guardar(estado, reg)}
    cambios, cerrada = pasar_dias(estado_parcial, DIAS_POR_NEGOCIACION)
    return {**cambios, "siguiente": "resumen_ventana" if cerrada else "centro_de_mando"}
