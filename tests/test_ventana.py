"""Pruebas de la ventana de fichajes (calendario, bandeja y comandos). Ejecutar con: python -m pytest"""
from config import DIAS_VENTANA
from ventana import avanzar, leer_comando, marcar_leidos, no_leidos, programar


def test_evento_llega_a_la_bandeja_el_dia_correcto():
    cal = programar([], dia_actual=1, dias_de_espera=3, tipo="respuesta_oferta", asunto="Responde el Inter")
    assert cal[0]["dia"] == 4
    dia, cal, bandeja, llegados, cerrada = avanzar(1, 2, cal, [])     # día 3: todavía no llega
    assert dia == 3 and bandeja == [] and len(cal) == 1
    dia, cal, bandeja, llegados, cerrada = avanzar(dia, 1, cal, bandeja)  # día 4: llega
    assert dia == 4 and cal == [] and bandeja[0]["asunto"] == "Responde el Inter"
    assert not bandeja[0]["leido"] and not cerrada


def test_respuesta_inmediata_llega_al_avanzar_un_dia():
    cal = programar([], dia_actual=5, dias_de_espera=0, tipo="x", asunto="inmediata")
    _, cal, bandeja, _, _ = avanzar(5, 1, cal, [])
    assert len(bandeja) == 1


def test_calendario_queda_ordenado_por_dia():
    cal = programar([], 1, 5, "x", "tarde")
    cal = programar(cal, 1, 2, "x", "temprano")
    assert [e["asunto"] for e in cal] == ["temprano", "tarde"]
    assert len({e["id"] for e in cal}) == 2


def test_cierre_automatico_al_pasar_el_ultimo_dia():
    dia, _, _, _, cerrada = avanzar(DIAS_VENTANA - 2, 1, [], [])
    assert dia == DIAS_VENTANA - 1 and not cerrada
    dia, _, _, _, cerrada = avanzar(DIAS_VENTANA, 1, [], [])
    assert dia == DIAS_VENTANA and cerrada


def test_marcar_leidos():
    bandeja = [{"id": 1, "leido": False}, {"id": 2, "leido": True}]
    assert len(no_leidos(bandeja)) == 1
    assert no_leidos(marcar_leidos(bandeja)) == []


def test_leer_comando():
    assert leer_comando("1") == ("buscar", None)
    assert leer_comando("3") == ("avanzar", 1)
    assert leer_comando("3 5") == ("avanzar", 5)
    assert leer_comando("avanzar 2") == ("avanzar", 2)
    assert leer_comando("3 cero") == ("invalido", None)
    assert leer_comando("3 -2") == ("invalido", None)
    assert leer_comando("") == ("invalido", None)
    assert leer_comando("9") == ("invalido", None)
    assert leer_comando("  CERRAR ") == ("cerrar", None)
