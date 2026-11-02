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
# VENTANA DE FICHAJES
# ======================================================================
DIAS_VENTANA = 30              # duración de la ventana; al pasar este día el mercado se cierra solo

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

# ======================================================================
# NEGOCIACIÓN CON EL CLUB VENDEDOR (Paso 14)
# ======================================================================
# --- Precio mínimo del vendedor = valor de referencia x factores (información privada del vendedor)
PESO_TITULAR = 1.25                 # el jugador es titular en su club
PESO_MEJOR_DE_SU_POSICION = 1.15    # es el de mayor rating de su posición en su club
PESO_CONTRATO = {1: 0.70, 2: 0.90}  # años de contrato restantes; con 3 o más el factor es 1.00
PESO_VETERANO = 0.85                # edad >= EDAD_VETERANO
PESO_JOVEN_CON_POTENCIAL = 1.10     # edad <= EDAD_JOVEN y potencial >= rating + MARGEN_JOVEN_POTENCIAL
MARGEN_JOVEN_POTENCIAL = 5
PESO_VENTA_RIVAL = 1.50             # el comprador es el rival del vendedor (o viceversa)
PESO_CAPITAN = 1.20                 # el jugador es el capitán
FACTOR_PRECIO_PEDIDO = 1.25         # precio pedido (primera exigencia) = precio mínimo x este factor

# --- Intransferible: solo sale pagando la cláusula
ANIOS_CONTRATO_INTRANSFERIBLE = 3   # titular + mejor de su posición + contrato >= esto + vendedor de nivel >= comprador

# --- Cómo valora el vendedor cada parte de una oferta
PESO_VARIABLES = 0.50               # 1 M€ en variables vale 0,5 M€ (pueden no cumplirse)
FACTOR_VALOR_REVENTA = 0.30         # % de reventa: vale pct x valor de referencia x este factor
FACTOR_VALOR_RECOMPRA = 0.15        # recompra: vale pct retenido x valor de referencia x este factor
TASA_DESCUENTO = 0.10               # tasa anual para traer a valor presente un pago en cuotas
MAX_CUOTAS = 4                      # pagos anuales máximos; la cláusula se paga siempre al contado
MAX_PCT_REVENTA = 50
MAX_PCT_RECOMPRA = 60

# --- Umbrales de decisión (fracción del precio mínimo, en valor presente)
UMBRAL_OFERTA_INICIAL = 0.60        # la oferta inicial abre la negociación desde este nivel
UMBRAL_OFERTA_RIDICULA = 0.40       # bajo este nivel el vendedor rompe de inmediato
UMBRAL_RUPTURA_LLM = 0.60           # el Selling Club Agent solo puede romper si la oferta está bajo este nivel

# --- Tiempos y rondas
MAX_RONDAS_CLUB = 5
DIAS_RESPUESTA_MIN = 1              # la respuesta a la oferta inicial nunca llega el mismo día
DIAS_POR_NEGOCIACION = 1            # cada negociación (club o jugador) consume este número de días
CONCESION_RESPALDO = 2.0            # forma de la regla de respaldo: >1 concede poco al inicio y más al final
