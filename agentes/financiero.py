"""Financial Agent: el código calcula la viabilidad y el modelo solo redacta un comentario."""
import json

from config import MAX_CUOTAS
from datos import analizar_viabilidad
from llm import consultar_json
from registro import emitir

SISTEMA_FINANCIERO = """Eres el Financial Agent de un club de fútbol: el auditor que revisa la viabilidad económica de cada fichaje candidato.
Recibirás en JSON una lista de candidatos con sus cifras ya calculadas por el sistema.

Reglas estrictas:
- Usa SOLO las cifras entregadas. No recalcules ni inventes montos.
- No cambies el veredicto entregado.
- Para cada candidato escribe un comentario de una sola frase (máximo 25 palabras) que cite al menos una cifra concreta.
- Copia el id de cada candidato tal como se entregó.

Responde SOLO con un objeto JSON con esta forma exacta:
{"comentarios": [{"id": 27, "comentario": "..."}]}"""


def analizar_finanzas(estado):
    """Nodo del Financial Agent: descarta candidatos inviables y comenta los demás."""
    analizados = []
    for c in estado["lista_corta"]:
        analisis = analizar_viabilidad(c, estado["resumen"])
        analizados.append({**c, "analisis": analisis, "comentario": ""})

    viables = []
    for c in analizados:
        if c["analisis"]["veredicto"] == "inviable":
            motivo = "; ".join(c["analisis"]["alertas"])
            emitir("descarte", f"Descartado por el Financial Agent: {c['nombre']} ({motivo})",
                   agente="financiero", jugador_id=c["id"])
        else:
            viables.append(c)

    if viables:
        datos = [{"id": c["id"], "nombre": c["nombre"], **c["analisis"]} for c in viables]
        try:
            respuesta = consultar_json(SISTEMA_FINANCIERO, json.dumps(datos, ensure_ascii=False),
                                       agente="financiero")
            comentarios = {int(x["id"]): x["comentario"] for x in respuesta.get("comentarios", [])}
            for c in viables:
                c["comentario"] = comentarios.get(c["id"], "")
        except Exception:
            emitir("aviso", "No se pudieron generar los comentarios del Financial Agent.", agente="financiero")

    vistos = {c["id"]: c for c in estado.get("candidatos_busqueda", [])}
    vistos.update({c["id"]: c for c in viables})
    return {"lista_final": viables, "candidatos_busqueda": list(vistos.values())}


# ------------------------------------------------------------- CONSEJO EN NEGOCIACIÓN
# El Financial Agent piensa y propone una oferta concreta; el código la valida (rangos, presupuesto,
# margen salarial) y calcula cuánto vale. No conoce el mínimo del vendedor ni el del jugador.
from config import FACTOR_VALOR_RECOMPRA, FACTOR_VALOR_REVENTA, PESO_VARIABLES, TASA_DESCUENTO

SISTEMA_CONSEJO_FINANCIERO = f"""Eres el Financial Agent de un club de fútbol. El director deportivo está negociando un
traspaso y te pide que DISEÑES la próxima oferta. Recibirás en JSON: presupuesto disponible, valor de mercado
estimado del jugador, la exigencia actual del vendedor (con su valor de hoy), la última oferta propia, las rondas
que quedan y el historial.

Cómo valora el vendedor una oferta (ya lo calcula el sistema; úsalo para pensar):
- El pago en cuotas se descuenta al {int(TASA_DESCUENTO * 100)} % anual: pagar en más cuotas alivia el presupuesto
  de hoy, pero el vendedor lo valora menos.
- Cada euro en variables vale {PESO_VARIABLES} para el vendedor (puede no cumplirse).
- El % de una futura venta y la opción de recompra suman valor sin gastar presupuesto hoy (factores
  {FACTOR_VALOR_REVENTA} y {FACTOR_VALOR_RECOMPRA} sobre el valor de mercado).

Tu objetivo: una oferta que tenga opciones reales de ser aceptada sin pagar de más. Nunca propongas algo que valga
más que la exigencia actual (sería mejor aceptarla) y respeta el presupuesto (cuenta solo la primera cuota).

Responde SOLO con un objeto JSON con esta forma exacta:
{{"oferta": {{"fijo": 0, "variables": 0, "pct_reventa": 0, "recompra_pct": 0, "recompra_temporadas": 0, "cuotas": 1}},
 "consejo": "2 o 3 frases, sin listas: qué ofrecer y por qué esa estructura"}}"""


def aconsejar(exigencia, presupuesto, valor_referencia, contexto_extra=None):
    """El agente diseña una oferta; el código la valida. Devuelve (texto_consejo, oferta_validada o None)."""
    from negociacion.reglas import describir_oferta, normalizar_oferta, primer_pago, valor_efectivo
    datos = {"presupuesto_disponible": presupuesto, "valor_mercado_estimado": valor_referencia,
             "exigencia_del_vendedor": describir_oferta(exigencia),
             "valor_hoy_de_la_exigencia": valor_efectivo(exigencia, valor_referencia), **(contexto_extra or {})}
    try:
        r = consultar_json(SISTEMA_CONSEJO_FINANCIERO, json.dumps(datos, ensure_ascii=False), agente="financiero_consejo")
    except Exception:
        return "El Financial Agent no pudo preparar una recomendación.", None
    oferta = normalizar_oferta(r.get("oferta"))
    texto = str(r.get("consejo") or "")
    if oferta["fijo"] <= 0:
        return texto or "El Financial Agent no propuso una oferta concreta.", None
    # Validaciones del código sobre la propuesta del agente
    notas = []
    while primer_pago(oferta) > presupuesto and oferta["cuotas"] < MAX_CUOTAS:
        oferta["cuotas"] += 1
        notas.append(f"se repartió en {oferta['cuotas']} cuotas para caber en el presupuesto")
    if primer_pago(oferta) > presupuesto:
        notas.append("aun así el primer pago supera el presupuesto")
    if valor_efectivo(oferta, valor_referencia) > valor_efectivo(exigencia, valor_referencia):
        notas.append("vale más que la exigencia actual: conviene más aceptarla")
    if notas:
        emitir("correccion_arbitro", "Revisión de la sugerencia del Financial: " + "; ".join(notas), agente="financiero")
    return texto, oferta


SISTEMA_CONSEJO_SALARIO = """Eres el Financial Agent de un club de fútbol. El director deportivo negocia el contrato de un
jugador y te pide que DISEÑES la próxima oferta. Recibirás en JSON: margen salarial, presupuesto disponible para
una prima, el salario actual estimado del jugador (un intervalo), su exigencia actual (con su valor anual), la
probabilidad de cumplir cada tipo de bono según su posición, la última oferta propia y las rondas que quedan.

Cómo funciona (ya lo calcula el sistema; úsalo para pensar):
- La masa salarial cuenta el salario fijo más el valor esperado de los bonos; la prima sale del presupuesto,
  no de la masa salarial.
- Para el jugador, la prima vale como salario repartido en los años del contrato, y un año opcional vale medio año.
- Un bono vale para el jugador su monto por la probabilidad de cumplirlo.

Tu objetivo: un contrato con opciones reales de ser aceptado que cuide la masa salarial. Nunca propongas algo que
valga más que la exigencia actual y respeta el margen salarial y el presupuesto.

Responde SOLO con un objeto JSON con esta forma exacta:
{"contrato": {"salario": 0, "bonos": {}, "anios": 0, "anio_opcional": false, "prima": 0},
 "consejo": "2 o 3 frases, sin listas: qué ofrecer y por qué esa estructura"}"""


def aconsejar_salario(datos, posicion, margen, presupuesto_prima):
    """El agente diseña un contrato; el código lo valida. Devuelve (texto_consejo, contrato_validado o None)."""
    from negociacion.reglas_jugador import costo_anual_club, normalizar_oferta_jugador
    try:
        r = consultar_json(SISTEMA_CONSEJO_SALARIO, json.dumps(datos, ensure_ascii=False), agente="financiero_consejo")
    except Exception:
        return "El Financial Agent no pudo preparar una recomendación.", None
    contrato = normalizar_oferta_jugador(r.get("contrato"))
    texto = str(r.get("consejo") or "")
    if contrato["salario"] <= 0 or contrato["anios"] <= 0:
        return texto or "El Financial Agent no propuso un contrato concreto.", None
    notas = []
    if costo_anual_club(contrato, posicion) > margen:
        notas.append("su costo anual supera el margen salarial")
    if contrato["prima"] > presupuesto_prima:
        notas.append("la prima supera el presupuesto disponible")
    if notas:
        emitir("correccion_arbitro", "Revisión de la sugerencia del Financial: " + "; ".join(notas), agente="financiero")
    return texto, contrato
