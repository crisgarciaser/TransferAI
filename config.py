"""Parámetros de diseño de TransferAI.

Todas las reglas numéricas del simulador están aquí, con nombre y comentario, para poder
modificarlas sin tocar la lógica. Los parámetros de construcción de la base de datos
(presupuesto, bonus europeo, etc.) están al inicio de convertir_datos.py.
"""

# ======================================================================
# MODELO DE LENGUAJE
# ======================================================================
TEMPERATURA = 0.2              # baja: respuestas estables en tareas de análisis
MAX_PASOS_HERRAMIENTAS = 12    # máximo de ciclos pensar-actuar-observar del Scouting Agent

# ======================================================================
# SCOUTING
# ======================================================================
MAX_RONDAS_SCOUTING = 3        # rondas de scouting por búsqueda
MAX_CANDIDATOS_POR_POSICION = 3
MAX_RESULTADOS_BUSQUEDA = 10   # jugadores que entrega buscar_jugadores por defecto
POSICIONES_VALIDAS = ["POR", "DFC", "LAT", "MED", "EXT", "DEL"]

# --- Clasificación del tipo de fichaje (evaluar_encaje)
EDAD_VETERANO = 30             # el mejor jugador actual se considera veterano desde esta edad
EDAD_JOVEN = 24                # un candidato es "joven" hasta esta edad
TOLERANCIA_RATING = 6          # un sucesor joven puede tener hasta estos puntos menos que el veterano
EDAD_PROMESA = 21              # un candidato es "promesa" hasta esta edad
MARGEN_POTENCIAL = 3           # el potencial de una promesa debe superar al mejor actual por estos puntos
TOLERANCIA_PROMESA = 10        # una promesa puede tener hasta estos puntos menos de rating que el mejor actual

# ======================================================================
# FINANZAS (Financial Agent)
# ======================================================================
UMBRAL_AJUSTADO_PRESUPUESTO = 70   # % del presupuesto de fichajes desde el que un fichaje es "ajustado"
UMBRAL_AJUSTADO_MARGEN = 50        # % del margen salarial desde el que un fichaje es "ajustado"
