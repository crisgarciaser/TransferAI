"""Pruebas de la negociación con el jugador, el plazo de 5 días y los datos en memoria."""
import os

import pytest

os.environ.setdefault("QWEN_API_KEY", "x")
os.environ.setdefault("QWEN_BASE_URL", "http://x")

from config import DIAS_PLAZO_JUGADOR, MAX_RONDAS_JUGADOR
from datos import (ajustar_presupuesto, cargar_jugadores, intervalo_salario, obtener_resumen_club,
                   registrar_traspaso, reiniciar_mercado)
from negociacion.reglas_jugador import (
    anios_preferidos, arbitrar_jugador, bonos_poco_probables, costo_anual_club, minimo_para_anios,
    perfil_jugador, proporcion, revela_privado, valor_anual_para_jugador,
)

JUGADOR = {"id": 7, "nombre": "Juanito", "posicion": "DEL", "edad": 26, "rating": 80, "potencial": 82,
           "salario_anual": 3.0, "reputacion_internacional": 2, "agencia": ""}
VENDEDOR = {"club": "A", "nivel": 7, "competicion_internacional": "champions"}
COMPRADOR = {"club": "B", "nivel": 5, "competicion_internacional": "no"}


@pytest.fixture
def perfil():
    return perfil_jugador(JUGADOR, VENDEDOR, COMPRADOR, sera_titular=True)


def test_exigencia_minima_con_factores(perfil):
    # baja 2 niveles (+20 %) y pierde competición europea (x1,15)
    assert perfil["salario_minimo"] == pytest.approx(3.0 * 1.2 * 1.15, abs=0.001)
    assert perfil["salario_pedido"] == pytest.approx(perfil["salario_minimo"] * 1.2, abs=0.001)


def test_rotacion_y_estrella():
    rotacion = perfil_jugador(JUGADOR, COMPRADOR, COMPRADOR, sera_titular=False)
    assert rotacion["salario_minimo"] == pytest.approx(3.0 * 0.9, abs=0.001)
    estrella = perfil_jugador({**JUGADOR, "rating": 88}, COMPRADOR, COMPRADOR, sera_titular=True)
    assert estrella["estrella"] and estrella["salario_minimo"] == pytest.approx(3.0 * 1.25, abs=0.001)
    assert estrella["umbral_ruptura"] > rotacion["umbral_ruptura"]


def test_anios_preferidos_segun_edad_y_club():
    grande, chico = {"nivel": 8}, {"nivel": 4}
    assert anios_preferidos({**JUGADOR, "edad": 20}, grande) == (4, 5)
    assert anios_preferidos({**JUGADOR, "edad": 20}, chico) == (2, 3)
    assert anios_preferidos({**JUGADOR, "edad": 32}, chico) == (3, 4)


def test_anios_fuera_de_rango_encarecen(perfil):
    dentro = minimo_para_anios(perfil, {"salario": 1, "anios": 3})
    fuera = minimo_para_anios(perfil, {"salario": 1, "anios": 6})
    assert fuera == pytest.approx(dentro * 1.10, abs=0.001)          # 2 años fuera: +10 %
    assert minimo_para_anios(perfil, {"salario": 1, "anios": 4, "anio_opcional": True}) == \
        pytest.approx(dentro * 1.025, abs=0.001)                      # 4 + 1 opcional = 4,5 años


def test_bonos_y_prima(perfil):
    base = valor_anual_para_jugador({"salario": 3, "anios": 3}, "DEL")
    con_bono = valor_anual_para_jugador({"salario": 3, "anios": 3, "bonos": {"goles": 1}}, "DEL")
    assert con_bono == pytest.approx(base + 0.6)                      # 60 % de probabilidad para un DEL
    assert valor_anual_para_jugador({"salario": 3, "anios": 3, "prima": 3}, "DEL") == pytest.approx(base + 1)
    assert bonos_poco_probables({"porterias_a_cero": 1, "goles": 1}, "DEL") == ["porterias_a_cero"]
    assert costo_anual_club({"salario": 3, "anios": 3, "prima": 3}, "DEL") == 3   # la prima no es masa salarial


def test_arbitro_jugador(perfil):
    baja = {"salario": perfil["salario_minimo"] * 0.9, "anios": 3}
    final, corr = arbitrar_jugador({"accion": "aceptar"}, baja, perfil, 1, {"salario": perfil["salario_pedido"], "anios": 4})
    assert final["accion"] == "contraofertar" and corr
    assert proporcion(final["contraoferta"], perfil) >= 1
    final, _ = arbitrar_jugador({"accion": "contraofertar", "contraoferta": {"salario": 99, "anios": 3}},
                                baja, perfil, MAX_RONDAS_JUGADOR, {"salario": perfil["salario_pedido"], "anios": 4})
    assert final["accion"] == "rechazar"


def test_no_revela_salario(perfil):
    assert revela_privado("Hoy cobra 3.0 millones", perfil)
    assert not revela_privado("Pedimos 5 millones", perfil)


def test_intervalo_contiene_salario_real():
    for j in cargar_jugadores()[:300]:
        minimo, maximo = intervalo_salario(j)
        assert minimo <= j["salario_anual"] + 0.01 and j["salario_anual"] - 0.01 <= maximo


def test_traspaso_actualiza_club_y_presupuesto():
    reiniciar_mercado()
    antes = obtener_resumen_club("Fiorentina")
    j = next(x for x in cargar_jugadores() if x["club"] == "Valencia")
    registrar_traspaso(j["id"], "Fiorentina", 2.0, 4)
    ajustar_presupuesto("Fiorentina", -10)
    despues = obtener_resumen_club("Fiorentina")
    assert despues["n_jugadores"] == antes["n_jugadores"] + 1
    assert despues["presupuesto_fichajes"] == pytest.approx(antes["presupuesto_fichajes"] - 10)
    assert despues["margen_salarial"] == pytest.approx(antes["margen_salarial"] - 2.0, abs=0.01)
    reiniciar_mercado()
    assert obtener_resumen_club("Fiorentina")["n_jugadores"] == antes["n_jugadores"]


def test_plazo_para_negociar_con_el_jugador():
    from negociacion.nodos_club import pasar_dias
    reg = {"jugador": {"nombre": "Juanito"}, "fase": "acuerdo_club", "dia_acuerdo": 4}
    estado = {"dia": 4 + DIAS_PLAZO_JUGADOR, "calendario": [], "bandeja": [], "negociaciones": {"7": reg}}
    cambios, _ = pasar_dias(estado, 1)
    assert cambios["negociaciones"]["7"]["fase"] == "fracasada"
    assert cambios["bandeja"][-1]["tipo"] == "plazo_vencido"
    estado["dia"] = 4
    cambios, _ = pasar_dias(estado, DIAS_PLAZO_JUGADOR)
    assert cambios["negociaciones"]["7"]["fase"] == "acuerdo_club"
