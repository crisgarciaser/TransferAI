"""Player Agent: el representante del jugador (su agencia real si se conoce).

El modelo decide cada ronda (aceptar, contraofertar o rechazar), con qué condiciones y con qué
argumento. Conoce el salario actual y la exigencia mínima del jugador, pero debe mantenerlos en
secreto. El código (negociacion/reglas_jugador.arbitrar_jugador) revisa la decisión.
"""
import json
import random

from config import PROB_ARGUMENTO_HUMANO
from llm import consultar_json
from registro import emitir

SISTEMA_AGENTE_JUGADOR = """Eres {quien}, y negocias el contrato de {jugador} con {club}, que ya acordó su traspaso
con el club actual. Hablas en español, como un representante real: {tono}, sin listas ni viñetas.

Recibirás en JSON la situación: el perfil del jugador, el rol que tendría, tus límites (SECRETOS), la
oferta actual del club (con su valor ya calculado por el sistema), tu última exigencia y el historial.

Cómo negociar:
- Tu objetivo es el mejor contrato posible para tu representado sin perder un acuerdo razonable.
- Nunca aceptes por debajo de la exigencia mínima. NUNCA reveles el salario actual ni el mínimo.
- Concede de a poco: cada contraoferta puede ser igual o menor que la anterior, nunca mayor.
- Puedes cambiar salario por otras cosas: años de contrato (tu representado prefiere entre
  {anios_min} y {anios_max} años), año opcional, prima de fichaje o bonos por objetivos.
- Los bonos que tu representado difícilmente cumplirá por su posición valen poco para él.
- Habla del jugador con expresiones, no con ratings ni potencial numéricos; varía los argumentos.
- Te quedan {rondas_restantes} ronda(s); en la última solo puedes aceptar o rechazar.

Responde SOLO con un objeto JSON con esta forma exacta:
{{"accion": "aceptar|contraofertar|rechazar",
 "contraoferta": {{"salario": 0, "bonos": {{}}, "anios": 0, "anio_opcional": false, "prima": 0}},
 "mensaje": "tu respuesta al club, 2 a 4 frases"}}"""

SISTEMA_REDACCION_JUGADOR = """Eres {quien}, y negocias el contrato de {jugador} con {club}. Ya se decidió tu respuesta;
solo debes redactarla en español, como un representante real ({tono}), en 2 a 4 frases y sin listas.
NUNCA menciones el salario actual ni la exigencia mínima. Usa SOLO las cifras entregadas.

Responde SOLO con un objeto JSON: {{"mensaje": "..."}}"""

# ARGUMENTO HUMANO (recurso ocasional): igual que en el Selling Club Agent; se controla con
# PROB_ARGUMENTO_HUMANO en config.py (0 para eliminarlo).
INSTRUCCION_ARGUMENTO_HUMANO = """
- Solo en este mensaje: puedes sumar UNA frase breve sobre lo que siente o quiere el jugador
  (su ilusión por el proyecto, su familia, su deseo de jugar), sin exagerar."""


def _quien(agencia):
    return f"un representante de la agencia {agencia}" if agencia else "el representante del jugador"


def _tono(estrella):
    return "firme y exigente, consciente de que representa a una figura" if estrella else "cordial y dispuesto a llegar a un acuerdo"


def decidir(contexto):
    sistema = SISTEMA_AGENTE_JUGADOR.format(
        quien=_quien(contexto["agencia"]), jugador=contexto["jugador"]["nombre"], club=contexto["club_comprador"],
        tono=_tono(contexto["estrella"]), anios_min=contexto["anios_preferidos"][0],
        anios_max=contexto["anios_preferidos"][1], rondas_restantes=contexto["rondas_restantes"])
    if random.random() < PROB_ARGUMENTO_HUMANO:
        sistema += INSTRUCCION_ARGUMENTO_HUMANO
    try:
        return consultar_json(sistema, json.dumps(contexto, ensure_ascii=False), agente="agente_jugador")
    except Exception:
        emitir("aviso", "El Player Agent no entregó una respuesta válida.", agente="agente_jugador")
        return None


def redactar(agencia, estrella, jugador, club, decision, cifras):
    sistema = SISTEMA_REDACCION_JUGADOR.format(quien=_quien(agencia), jugador=jugador, club=club, tono=_tono(estrella))
    try:
        return consultar_json(sistema, json.dumps({"decision": decision, "cifras": cifras}, ensure_ascii=False),
                              agente="agente_jugador_redaccion")["mensaje"]
    except Exception:
        return None
