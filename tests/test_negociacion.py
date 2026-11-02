"""Pruebas de las reglas de la negociación con el club vendedor (negociacion/reglas.py)."""
import pytest

from config import MAX_RONDAS_CLUB
from negociacion.reglas import (
    arbitrar, decision_respaldo, desempeno, es_ridicula, evaluar_oferta_inicial, normalizar_oferta,
    peticion_respaldo, perfil_vendedor, primer_pago, revela_minimo, valor_efectivo, valor_presente,
)

JUGADOR = {"id": 1, "nombre": "Juanito Pérez", "posicion": "MED", "valor_mercado": 40.0, "rating": 82,
           "potencial": 84, "edad": 26, "titular": "si", "anios_contrato": 4, "clausula_rescision": 120.0,
           "capitan": "no"}
COMPANERO = {**JUGADOR, "id": 2, "rating": 78, "titular": "no"}
VENDEDOR = {"club": "Club A", "rival": "Club C", "nivel": 6}
COMPRADOR = {"club": "Club B", "rival": "Club D", "nivel": 7}


@pytest.fixture
def perfil():
    return perfil_vendedor(JUGADOR, [JUGADOR, COMPANERO], VENDEDOR, COMPRADOR)


def test_precio_minimo_aplica_factores(perfil):
    # titular x1.25 y mejor de su posición x1.15 sobre 40 M€
    assert perfil["precio_minimo"] == pytest.approx(40 * 1.25 * 1.15, abs=0.01)
    assert perfil["precio_pedido"] == pytest.approx(perfil["precio_minimo"] * 1.25, abs=0.01)
    assert not perfil["intransferible"]          # el vendedor es de menor nivel que el comprador


def test_venta_a_rival_y_tope_en_clausula():
    rival = {**COMPRADOR, "club": "Club C"}
    p = perfil_vendedor({**JUGADOR, "clausula_rescision": 60.0}, [JUGADOR], VENDEDOR, rival)
    assert p["es_rival"] and p["precio_minimo"] == 60.0 and p["precio_pedido"] == 60.0


def test_intransferible_si_vendedor_es_de_igual_o_mayor_nivel():
    p = perfil_vendedor(JUGADOR, [JUGADOR], {**VENDEDOR, "nivel": 8}, COMPRADOR)
    assert p["intransferible"]
    assert evaluar_oferta_inicial("oferta", {"fijo": 500}, p)["resultado"] == "solo_clausula"
    assert evaluar_oferta_inicial("clausula", {"fijo": 120, "clausula": True}, p)["resultado"] == "acepta_clausula"


def test_valor_presente_de_cuotas():
    assert valor_presente(100, 1) == pytest.approx(100)
    assert valor_presente(100, 4) == pytest.approx(25 * (1 + 1 / 1.1 + 1 / 1.1 ** 2 + 1 / 1.1 ** 3))
    assert primer_pago({"fijo": 100, "cuotas": 4}) == 25
    assert primer_pago({"fijo": 100, "cuotas": 4, "clausula": True}) == 100   # la cláusula va al contado


def test_variables_reventa_y_recompra_suman_valor():
    base = valor_efectivo({"fijo": 30}, 40)
    assert valor_efectivo({"fijo": 30, "variables": 10}, 40) == pytest.approx(base + 5)
    assert valor_efectivo({"fijo": 30, "pct_reventa": 10}, 40) > base
    assert valor_efectivo({"fijo": 30, "recompra_pct": 40, "recompra_temporadas": 2}, 40) > base


def test_normalizar_oferta_acota_valores():
    o = normalizar_oferta({"fijo": -5, "cuotas": 9, "pct_reventa": 99, "variables": "abc"})
    assert o["fijo"] == 0 and o["cuotas"] == 4 and o["pct_reventa"] == 50 and o["variables"] == 0


def test_respuesta_inicial_segun_umbrales(perfil):
    minimo = perfil["precio_minimo"]
    assert evaluar_oferta_inicial("interes", None, perfil)["resultado"] == "abre"
    assert evaluar_oferta_inicial("oferta", {"fijo": minimo * 0.3}, perfil)["resultado"] == "rechaza"
    assert evaluar_oferta_inicial("oferta", {"fijo": minimo * 0.5}, perfil)["resultado"] == "rechaza"
    assert evaluar_oferta_inicial("oferta", {"fijo": minimo * 0.7}, perfil)["resultado"] == "abre"
    for intencion in ("interes", "oferta"):
        assert evaluar_oferta_inicial(intencion, {"fijo": minimo}, perfil)["dias"] >= 1


def test_respaldo_parte_del_pedido_y_llega_al_minimo(perfil):
    assert peticion_respaldo(perfil, 0)["fijo"] == pytest.approx(perfil["precio_pedido"])
    assert peticion_respaldo(perfil, MAX_RONDAS_CLUB)["fijo"] == pytest.approx(perfil["precio_minimo"])
    montos = [peticion_respaldo(perfil, r)["fijo"] for r in range(MAX_RONDAS_CLUB + 1)]
    assert montos == sorted(montos, reverse=True)


def test_arbitro_no_acepta_bajo_el_minimo(perfil):
    baja = {"fijo": perfil["precio_minimo"] * 0.8}
    final, corr = arbitrar({"accion": "aceptar"}, baja, perfil, 2, {"fijo": perfil["precio_pedido"]})
    assert final["accion"] == "contraofertar" and corr
    assert valor_efectivo(final["contraoferta"], 40) >= perfil["precio_minimo"]


def test_arbitro_no_pide_mas_que_antes(perfil):
    anterior = {"fijo": perfil["precio_minimo"] + 3}
    final, corr = arbitrar({"accion": "contraofertar", "contraoferta": {"fijo": perfil["precio_pedido"] + 20}},
                           {"fijo": perfil["precio_minimo"] * 0.8}, perfil, 2, anterior)
    assert final["contraoferta"]["fijo"] == anterior["fijo"] and corr


def test_arbitro_no_pide_bajo_su_minimo(perfil):
    final, _ = arbitrar({"accion": "contraofertar", "contraoferta": {"fijo": 1}},
                        {"fijo": 0.5 * perfil["precio_minimo"] + 1}, perfil, 2, {"fijo": perfil["precio_pedido"]})
    assert valor_efectivo(final["contraoferta"], 40) >= perfil["precio_minimo"]


def test_arbitro_contraoferta_menor_que_la_oferta_es_aceptar(perfil):
    oferta = {"fijo": perfil["precio_minimo"] + 5}
    final, corr = arbitrar({"accion": "contraofertar", "contraoferta": {"fijo": perfil["precio_minimo"] + 1}},
                           oferta, perfil, 2, {"fijo": perfil["precio_pedido"]})
    assert final["accion"] == "aceptar" and corr


def test_arbitro_ultima_ronda_solo_acepta_o_rechaza(perfil):
    final, _ = arbitrar({"accion": "contraofertar", "contraoferta": {"fijo": perfil["precio_pedido"]}},
                        {"fijo": perfil["precio_minimo"] + 1}, perfil, MAX_RONDAS_CLUB, {"fijo": perfil["precio_pedido"]})
    assert final["accion"] == "aceptar"
    final, _ = arbitrar({"accion": "contraofertar", "contraoferta": {"fijo": perfil["precio_pedido"]}},
                        {"fijo": perfil["precio_minimo"] * 0.9}, perfil, MAX_RONDAS_CLUB, {"fijo": perfil["precio_pedido"]})
    assert final["accion"] == "rechazar"


def test_arbitro_impide_romper_con_oferta_razonable(perfil):
    final, corr = arbitrar({"accion": "rechazar"}, {"fijo": perfil["precio_minimo"] * 0.9}, perfil, 2,
                           {"fijo": perfil["precio_pedido"]})
    assert final["accion"] == "contraofertar" and corr


def test_arbitro_respuesta_invalida_usa_respaldo(perfil):
    final, corr = arbitrar(None, {"fijo": perfil["precio_minimo"] * 0.8}, perfil, 1, {"fijo": perfil["precio_pedido"]})
    assert final["accion"] in ("aceptar", "contraofertar", "rechazar") and corr


def test_respaldo_acepta_si_la_oferta_cubre_su_peticion(perfil):
    assert decision_respaldo({"fijo": perfil["precio_pedido"]}, perfil, 1, None)["accion"] == "aceptar"


def test_oferta_ridicula(perfil):
    assert es_ridicula({"fijo": perfil["precio_minimo"] * 0.3}, perfil)
    assert not es_ridicula({"fijo": perfil["precio_minimo"] * 0.5}, perfil)


def test_detecta_filtracion_del_minimo(perfil):
    minimo = perfil["precio_minimo"]
    assert revela_minimo(f"Nunca bajaríamos de {minimo} millones", perfil)
    assert revela_minimo(f"Nunca bajaríamos de {str(minimo).replace('.', ',')} millones", perfil)
    assert not revela_minimo("Pedimos 70 millones", perfil)
    assert not revela_minimo(f"Aceptamos {minimo}", perfil, cifras_permitidas=[minimo])


def test_desempeno(perfil):
    d = desempeno(perfil, precio_acordado={"fijo": perfil["precio_minimo"]})
    assert d["captura_pct"] == 100 and d["sobrepago"] == pytest.approx(0, abs=0.01)
    d = desempeno(perfil, precio_acordado={"fijo": perfil["precio_pedido"]})
    assert d["captura_pct"] == 0
    d = desempeno(perfil, ultima_oferta={"fijo": perfil["precio_minimo"] - 4})
    assert d["resultado"] == "fracaso" and d["faltaron"] == pytest.approx(4, abs=0.01)
