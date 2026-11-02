"""Selling Club Agent: el director deportivo del club dueño del jugador.

El modelo decide cada ronda (aceptar, contraofertar o rechazar), con qué cifras y con qué
argumento. Conoce su propio precio mínimo, pero debe mantenerlo en secreto. El código
(negociacion/reglas.arbitrar) revisa la decisión antes de que llegue al usuario.
"""
import json

from llm import consultar_json
from registro import emitir

SISTEMA_VENDEDOR = """Eres el director deportivo del club {club}, dueño del jugador {jugador}. Otro club quiere
comprarlo y tú negocias su traspaso. Hablas en primera persona, en español, como un dirigente real:
cordial pero firme, sin listas ni viñetas.

Recibirás en JSON la situación: datos del jugador y de ambos clubes, tus límites (SECRETOS), la oferta
actual del comprador (con su valor ya calculado por el sistema), tu última exigencia y el historial.

Cómo negociar:
- Tu objetivo es vender lo más caro posible sin perder un acuerdo razonable.
- Nunca aceptes por debajo de tu precio mínimo. NUNCA reveles tu precio mínimo ni lo insinúes.
- Concede de a poco: cada contraoferta puede ser igual o menor que tu exigencia anterior, nunca mayor.
- Puedes pedir condiciones en vez de solo dinero: variables, % de una futura venta, opción de recompra
  o cambiar el número de cuotas. Úsalas para acercar posiciones.
- Si el comprador paga en cuotas, recuerda que el dinero futuro vale menos (el sistema ya lo descontó).
- Argumenta con datos concretos del jugador (edad, rating, contrato, rol en tu equipo).
- Si la oferta está muy lejos de lo razonable puedes rechazar y dar por terminada la negociación.
- Te quedan {rondas_restantes} ronda(s); en la última solo puedes aceptar o rechazar.

Responde SOLO con un objeto JSON con esta forma exacta:
{{"accion": "aceptar|contraofertar|rechazar",
 "contraoferta": {{"fijo": 0, "variables": 0, "pct_reventa": 0, "recompra_pct": 0, "recompra_temporadas": 0, "cuotas": 1}},
 "mensaje": "tu respuesta al comprador, 2 a 4 frases"}}
Si aceptas o rechazas, "contraoferta" puede ir vacía."""

SISTEMA_REDACCION = """Eres el director deportivo del club {club}, dueño del jugador {jugador}. Ya se decidió tu respuesta
a la oferta del otro club; solo debes redactarla en primera persona, en español, como un dirigente real,
cordial pero firme, en 2 a 4 frases y sin listas. NUNCA menciones tu precio mínimo.

Recibirás en JSON la decisión y las cifras exactas que debes comunicar. Usa SOLO esas cifras.

Responde SOLO con un objeto JSON: {{"mensaje": "..."}}"""


def decidir(contexto):
    """Pide al modelo la decisión de esta ronda. Devuelve el diccionario del modelo (o None si falla)."""
    sistema = SISTEMA_VENDEDOR.format(club=contexto["club_vendedor"], jugador=contexto["jugador"]["nombre"],
                                      rondas_restantes=contexto["rondas_restantes"])
    try:
        return consultar_json(sistema, json.dumps(contexto, ensure_ascii=False), agente="club_vendedor")
    except Exception:
        emitir("aviso", "El Selling Club Agent no entregó una respuesta válida.", agente="club_vendedor")
        return None


def redactar(club, jugador, decision, cifras):
    """Redacta el mensaje de una decisión ya tomada (cuando el árbitro corrigió al modelo o en el primer contacto)."""
    sistema = SISTEMA_REDACCION.format(club=club, jugador=jugador)
    datos = {"decision": decision, "cifras": cifras}
    try:
        return consultar_json(sistema, json.dumps(datos, ensure_ascii=False), agente="club_vendedor")["mensaje"]
    except Exception:
        return None
