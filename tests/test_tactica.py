"""Pruebas del encaje táctico (tactica.py)."""
from tactica import encaje_tactico, identidad_tactica, perfil_tactico, pesos_para, rasgos_formacion

CLUB_POSESION = {"club": "A", "formacion": "4-3-3", "estilo_defensivo": "equilibrado",
                 "construccion": "construcción lenta", "creacion_ocasiones": "posesión",
                 "anchura_ofensiva": 50, "jugadores_en_area": 4}
CLUB_DIRECTO = {**CLUB_POSESION, "construccion": "construcción rápida",
                "creacion_ocasiones": "desmarques en profundidad"}


def med(**at):
    base = {"id": 1, "posicion": "MED", "rating": 80}
    return {**base, **{f"at_{k}": v for k, v in at.items()}}


ORGANIZADOR = med(ritmo=60, tiro=70, pase=90, regate=82, defensa=60, fisico=60, cabezazo=50, vision=90, resistencia=75)
VELOZ = med(ritmo=92, tiro=70, pase=68, regate=82, defensa=60, fisico=70, cabezazo=50, vision=66, resistencia=80)


def test_perfiles():
    assert perfil_tactico(ORGANIZADOR) == "organizador"
    assert perfil_tactico({**ORGANIZADOR, "at_defensa": 92, "at_vision": 70}) == "pivote defensivo"
    assert perfil_tactico({"posicion": "DEL", "at_cabezazo": 85, "at_fisico": 82}) == "delantero de área"


def test_el_estilo_cambia_los_pesos():
    assert pesos_para("MED", CLUB_POSESION)["pase"] > pesos_para("MED", CLUB_DIRECTO)["pase"]
    assert pesos_para("MED", CLUB_DIRECTO).get("ritmo", 0) > pesos_para("MED", CLUB_POSESION).get("ritmo", 0)


def test_el_mismo_jugador_encaja_distinto_segun_el_club():
    # el organizador calza mejor en el club de posesión; el veloz, en el club directo
    assert encaje_tactico(ORGANIZADOR, CLUB_POSESION, [])["encaje_tactico"] > \
        encaje_tactico(ORGANIZADOR, CLUB_DIRECTO, [])["encaje_tactico"]
    assert encaje_tactico(VELOZ, CLUB_DIRECTO, [])["encaje_tactico"] > \
        encaje_tactico(VELOZ, CLUB_POSESION, [])["encaje_tactico"]


def test_compara_con_el_mejor_actual():
    actual = {**VELOZ, "id": 2}
    r = encaje_tactico(ORGANIZADOR, CLUB_POSESION, [actual])
    assert r["encaje_del_mejor_actual"] is not None and r["nivel_encaje"] in ("alto", "medio", "bajo")


def test_formacion_y_descripcion():
    assert "linea_de_3" in rasgos_formacion("3-5-2") and "dos_delanteros" in rasgos_formacion("3-5-2")
    assert "posesión" in identidad_tactica(CLUB_POSESION)["descripcion"]