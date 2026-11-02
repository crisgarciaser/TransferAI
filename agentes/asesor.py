"""Asesor (Manager + Financial Agent): aconseja al director deportivo durante una negociación.

Solo recibe información que conoce el club comprador: nunca ve el precio mínimo del vendedor.
"""
import json

from llm import consultar_json
from registro import emitir

SISTEMA_ASESOR = """Eres el equipo asesor del director deportivo de {club}: el Manager (lo deportivo) y el
Financial Agent (lo económico). Están en medio de la negociación por {jugador}.

Recibirás en JSON lo que sabe tu club: valor de mercado estimado del jugador, presupuesto disponible,
la última exigencia del vendedor, la última oferta propia, las rondas que quedan y el historial.
No conoces el precio mínimo del vendedor: no lo inventes.

Da un consejo breve (3 a 5 frases, sin listas): si conviene subir, mantener o retirarse; una cifra o
estructura concreta para la próxima oferta (por ejemplo, mover dinero a variables o a cuotas, o
ofrecer % de reventa), y el riesgo principal. Usa solo cifras del JSON o derivadas de ellas.

Responde SOLO con un objeto JSON: {{"consejo": "..."}}"""


def aconsejar(club, jugador, contexto):
    sistema = SISTEMA_ASESOR.format(club=club, jugador=jugador)
    try:
        return consultar_json(sistema, json.dumps(contexto, ensure_ascii=False), agente="asesor")["consejo"]
    except Exception:
        emitir("aviso", "El asesor no pudo generar un consejo.", agente="asesor")
        return None
