"""Financial Agent: el código calcula la viabilidad y el modelo solo redacta un comentario."""
import json

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
