"""Herramienta de interpretación: convierte lo que escribe el director deportivo en una intención y una oferta.

No es un agente (no tiene objetivos propios ni negocia): es un traductor que usa el modelo de lenguaje.
El usuario escribe como una persona ("Saludos, ofrecemos 100 millones por Colina"); el modelo
identifica qué quiere decir y el código valida las cifras (rangos y presupuesto).
"""
import json

from config import MAX_CUOTAS, MAX_PCT_RECOMPRA, MAX_PCT_REVENTA
from llm import consultar_json
from negociacion.reglas import normalizar_oferta
from registro import emitir

SISTEMA_INTERPRETE = f"""Eres el asistente del director deportivo de un club de fútbol. Tu tarea es interpretar el
mensaje que el director quiere enviar al club dueño de un jugador y convertirlo en datos.

Recibirás en JSON: el mensaje, la etapa ("primer_contacto" o "ronda") y, si existe, la última
exigencia del club vendedor.

Clasifica la intención en una de estas:
- "interes": muestra interés o pide negociar, pero NO propone cifras.
- "oferta": propone cifras concretas.
- "clausula": dice que paga la cláusula de rescisión.
- "aceptar_condiciones": acepta la última exigencia del club vendedor tal como está.
- "consejo": pide ayuda o consejo a su propio equipo (no es un mensaje para el otro club).
- "retirarse": abandona la negociación.
- "otro": no se entiende o no tiene relación.

Reglas para las cifras (montos en millones de euros):
- Un monto sin más detalle es pago FIJO ("100 millones" -> fijo 100, variables 0).
- "variables", "bonus", "por objetivos" o "incentivos" van en variables.
- "X% de una futura venta" o "porcentaje de reventa" va en pct_reventa (0 a {MAX_PCT_REVENTA}).
- Recompra: "opción de recompra reteniendo X%" -> recompra_pct (0 a {MAX_PCT_RECOMPRA}) y recompra_temporadas.
- "en N cuotas/pagos/años" -> cuotas N (1 a {MAX_CUOTAS}); si no se dice, cuotas 1.
- No inventes cifras que el mensaje no dice; los campos no mencionados van en 0.
- Marca "ambigua": true SOLO si una cifra admite dos lecturas razonables (por ejemplo, "100 con 10
  en variables" puede ser 100 + 10 o 90 + 10), y explica la duda en "duda".

Responde SOLO con un objeto JSON con esta forma exacta:
{{"intencion": "oferta", "oferta": {{"fijo": 0, "variables": 0, "pct_reventa": 0, "recompra_pct": 0,
"recompra_temporadas": 0, "cuotas": 1}}, "ambigua": false, "duda": "", "resumen": "frase breve con lo entendido"}}"""

INTENCIONES = {"interes", "oferta", "clausula", "aceptar_condiciones", "consejo", "retirarse", "otro"}


def interpretar(mensaje, etapa, ultima_exigencia=None):
    """Devuelve {"intencion", "oferta", "ambigua", "duda", "resumen"} ya validado por el código."""
    datos = {"mensaje": mensaje, "etapa": etapa}
    if ultima_exigencia:
        datos["ultima_exigencia_del_vendedor"] = ultima_exigencia
    try:
        r = consultar_json(SISTEMA_INTERPRETE, json.dumps(datos, ensure_ascii=False), agente="interprete")
    except Exception:
        emitir("aviso", "No se pudo interpretar el mensaje; intenta escribirlo de otra forma.", agente="interprete")
        return {"intencion": "otro", "oferta": normalizar_oferta({}), "ambigua": False, "duda": "", "resumen": ""}

    intencion = r.get("intencion") if r.get("intencion") in INTENCIONES else "otro"
    oferta = normalizar_oferta(r.get("oferta"))
    # Validaciones del código sobre lo que entendió el modelo
    if intencion == "oferta" and oferta["fijo"] <= 0:
        intencion = "interes" if etapa == "primer_contacto" else "otro"
    if intencion == "clausula":
        oferta = normalizar_oferta({"clausula": True})
    return {"intencion": intencion, "oferta": oferta, "ambigua": bool(r.get("ambigua")),
            "duda": str(r.get("duda") or ""), "resumen": str(r.get("resumen") or "")}
