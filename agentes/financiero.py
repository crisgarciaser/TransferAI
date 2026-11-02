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

    return {"lista_final": viables}


# ------------------------------------------------------------- CONSEJO EN NEGOCIACIÓN
SISTEMA_CONSEJO_FINANCIERO = """Eres el Financial Agent de un club de fútbol. El director deportivo está negociando un
fichaje y te pide tu opinión ECONÓMICA. Recibirás en JSON cifras ya calculadas por el sistema: presupuesto,
primer pago de la exigencia actual del vendedor al contado y en cuotas, y si cabe en el presupuesto.

En 2 o 3 frases y sin listas: di si la exigencia actual es pagable y qué estructura conviene (al contado,
en cuotas, mover parte a variables o a % de reventa), citando al menos una cifra.
Usa SOLO las cifras entregadas; no recalcules ni inventes montos. No conoces el mínimo del vendedor.

Responde SOLO con un objeto JSON: {"consejo": "..."}"""


def cifras_consejo(exigencia_fijo, presupuesto):
    """El código calcula el primer pago de la exigencia actual al contado y en cuotas."""
    pagos = {f"{n}_cuota(s)": round(exigencia_fijo / n, 2) for n in range(1, MAX_CUOTAS + 1)}
    cabe = [n for n in range(1, MAX_CUOTAS + 1) if exigencia_fijo / n <= presupuesto]
    return {"presupuesto_disponible": presupuesto, "exigencia_fija_del_vendedor": exigencia_fijo,
            "primer_pago_segun_cuotas": pagos,
            "cuotas_minimas_para_que_quepa": cabe[0] if cabe else None}


def aconsejar(exigencia_fijo, presupuesto, contexto_extra=None):
    """Consejo económico del Financial Agent: cifras del código + comentario del modelo."""
    cifras = cifras_consejo(exigencia_fijo, presupuesto)
    try:
        r = consultar_json(SISTEMA_CONSEJO_FINANCIERO,
                           json.dumps({**cifras, **(contexto_extra or {})}, ensure_ascii=False), agente="financiero")
        return r["consejo"]
    except Exception:
        n = cifras["cuotas_minimas_para_que_quepa"]
        return (f"La exigencia de {exigencia_fijo} M€ cabe en el presupuesto si se paga en {n} cuota(s)." if n
                else f"La exigencia de {exigencia_fijo} M€ no cabe en el presupuesto de {presupuesto} M€ ni en "
                     f"{MAX_CUOTAS} cuotas.")


SISTEMA_CONSEJO_SALARIO = """Eres el Financial Agent de un club de fútbol. El director deportivo negocia el contrato de un
jugador y te pide tu opinión ECONÓMICA. Recibirás en JSON cifras ya calculadas por el sistema: margen salarial
disponible, la exigencia actual del jugador y su costo anual, el presupuesto que queda para la prima y el
intervalo estimado del salario actual del jugador.

En 2 o 3 frases y sin listas: di si la exigencia cabe en la masa salarial y qué conviene ofrecer (más años
con menos salario, bonos por objetivos o una prima en vez de salario fijo), citando al menos una cifra.
Usa SOLO las cifras entregadas. No conoces la exigencia mínima del jugador.

Responde SOLO con un objeto JSON: {"consejo": "..."}"""


def aconsejar_salario(cifras):
    """Consejo económico durante la negociación con el jugador (cifras calculadas por el código)."""
    try:
        return consultar_json(SISTEMA_CONSEJO_SALARIO, json.dumps(cifras, ensure_ascii=False),
                              agente="financiero")["consejo"]
    except Exception:
        cabe = cifras["costo_anual_exigencia"] <= cifras["margen_salarial"]
        return (f"La exigencia cuesta {cifras['costo_anual_exigencia']} M€ por temporada y el margen salarial es "
                f"{cifras['margen_salarial']} M€: " + ("cabe." if cabe else "no cabe; conviene usar bonos o una prima."))
