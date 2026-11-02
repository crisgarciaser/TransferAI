"""Interfaz de terminal de TransferAI.

Es la única parte del programa que imprime en pantalla y lee del teclado:
- mostrar_evento() recibe cada evento que emiten los agentes y lo muestra.
- preguntar() recibe una pausa humana del grafo (según su "tipo") y devuelve la respuesta del usuario.
Una interfaz HTML futura solo tendría que reemplazar estas dos funciones.
"""
import unicodedata

from langgraph.types import Command

from datos import cargar_clubes
from grafo import app
from registro import emitir, iniciar_sesion, suscribir

ORDEN_POSICIONES = ["POR", "DFC", "LAT", "MED", "EXT", "DEL"]


# ---------------------------------------------------------------- EVENTOS
def mostrar_plantilla(resumen, plantilla):
    r = resumen
    print(f"\n=== PLANTILLA DE {r['club'].upper()} ===")
    print(f"Presupuesto de fichajes: {r['presupuesto_fichajes']} | Tope salarial: {r['tope_salarial']} | "
          f"Masa salarial: {r['masa_salarial_actual']} | Margen: {r['margen_salarial']} (millones de euros)")
    for pos in ORDEN_POSICIONES:
        grupo = sorted((j for j in plantilla if j["posicion"] == pos), key=lambda j: j["rating"], reverse=True)
        if not grupo:
            continue
        print(f"\n{pos} ({len(grupo)})")
        for j in grupo:
            titular = "titular" if j["titular"] == "si" else "suplente"
            print(f"  {j['nombre']:<22} {j['edad']:>2} años  rating {j['rating']:>2}  "
                  f"pot {j.get('potencial', '-'):>2}  {titular:<8}  contrato {j['anios_contrato']} a  "
                  f"salario {j['salario_anual']:>6}  valor {j['valor_mercado']:>6}")


def mostrar_evento(evento):
    """Decide cómo se ve en pantalla cada tipo de evento."""
    tipo, mensaje, datos = evento["tipo"], evento["mensaje"], evento["datos"]
    if tipo == "plantilla":
        mostrar_plantilla(datos["resumen"], datos["plantilla"])
    elif tipo == "agente":
        print(f"\n--- {mensaje} ---")
    elif tipo == "herramienta":
        print(f"  ACTUAR: {mensaje}")
    elif tipo in ("aviso", "error"):
        print(f"{tipo.upper()}: {mensaje}")
    elif tipo == "descarte":
        print(mensaje)
    # "info" y "llm" quedan solo en el log para no saturar la pantalla


# ---------------------------------------------------------------- PAUSAS HUMANAS
def preguntar(pausa):
    """Muestra la pausa del grafo y devuelve lo que escribe el usuario."""
    tipo = pausa["tipo"]

    if tipo == "menu_plantilla":
        print(f"\n=== {pausa['club']} cargado ({pausa['n_jugadores']} jugadores) ===")
        print("1. Ver la plantilla y luego continuar con las recomendaciones")
        print("2. Ir directo a las recomendaciones")
        return input("¿Qué quieres hacer? (1 o 2): ")

    if tipo == "confirmar_prioridades":
        print("\n=== PROPUESTA DEL MANAGER AGENT ===")
        for p in pausa["propuestas"]:
            print(f"- {p['posicion']} (urgencia {p['urgencia']}): {p['motivo']}")
        print(f"\nPosiciones válidas: {', '.join(pausa['posiciones_validas'])}")
        return input("¿Qué posiciones quieres priorizar? (separa con comas, ej: DFC,MED): ")

    if tipo == "elegir_objetivo":
        print(f"\n=== CANDIDATOS EVALUADOS (ronda {pausa['intentos']}) ===")
        if not pausa["candidatos"]:
            print("No hay candidatos viables en esta ronda.")
        for c in pausa["candidatos"]:
            a = c["analisis"]
            tipo_fichaje = c.get("tipo_de_fichaje", "").replace("_", " ")
            print(f"[id {c['id']}] {c['nombre']} ({c['posicion']}, {c['edad']} años, {c['club']}) "
                  f"rating {c['rating']} - {tipo_fichaje} - {a['veredicto'].upper()}")
            print(f"   Traspaso estimado {a['traspaso_estimado']} | salario {a['salario_anual']} | "
                  f"presupuesto restante {a['presupuesto_restante']} | "
                  f"margen salarial restante {a['margen_salarial_restante']}")
            print(f"   Scout: {c['justificacion']}")
            if c.get("comentario"):
                print(f"   Financial: {c['comentario']}")
        return input("\nEscribe el id del jugador a fichar, 'nueva' (o 'nueva: más jóvenes') "
                     "para otra ronda de scouting, o 'salir': ")

    raise ValueError(f"Tipo de pausa desconocido: {tipo}")


# ---------------------------------------------------------------- INICIO
def _normalizar(texto):
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower().strip()


def elegir_club():
    clubes = [c["club"] for c in cargar_clubes()]
    while True:
        texto = _normalizar(input("\nEscribe el club que quieres gestionar (o parte del nombre): "))
        if not texto:
            continue
        exactas = [c for c in clubes if _normalizar(c) == texto]
        if exactas:
            return exactas[0]
        coincidencias = [c for c in clubes if texto in _normalizar(c)]
        if len(coincidencias) == 1:
            return coincidencias[0]
        if not coincidencias:
            print("No encontré ningún club con ese nombre. Intenta de nuevo.")
        else:
            print("Hay varias coincidencias:", ", ".join(coincidencias[:10]))


def main():
    archivo_log = iniciar_sesion()
    suscribir(mostrar_evento)
    print(f"TransferAI | registro de la sesión: {archivo_log.name}")

    config = {"configurable": {"thread_id": archivo_log.stem}}
    club = elegir_club()
    resultado = app.invoke({"club": club}, config)

    # Cada vez que el grafo se detiene en una pausa humana, se pregunta al usuario y se reanuda
    while "__interrupt__" in resultado:
        pausa = resultado["__interrupt__"][0].value
        respuesta = preguntar(pausa)
        emitir("respuesta_usuario", respuesta, pausa=pausa["tipo"])
        resultado = app.invoke(Command(resume=respuesta), config)

    print("\nPrioridades confirmadas:", resultado.get("prioridades_confirmadas"))
    print("\n=== RESULTADO ===")
    objetivo = resultado.get("jugador_objetivo")
    if objetivo:
        print(f"Jugador objetivo: {objetivo['nombre']} ({objetivo['posicion']}, {objetivo['edad']} años, "
              f"{objetivo['club']}), rating {objetivo['rating']}")
        print("Listo para iniciar la negociación.")
    else:
        print("No se eligió ningún jugador objetivo.")
    print()


if __name__ == "__main__":
    main()
