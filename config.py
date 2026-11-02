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
# Agentes que usan el modo de razonamiento del modelo (escribe un borrador interno antes de responder).
# Es lento y consume más tokens; solo se deja donde ayuda a decidir. El resto responde directo.
# Etiquetas posibles: "scouting", "manager" (diagnóstico), "manager_consejo", "financiero",
# "club_vendedor" (decisión de cada ronda), "club_vendedor_redaccion" (solo redacta), "interprete",
# "agente_jugador" (decisión de cada ronda) y "agente_jugador_redaccion".
AGENTES_CON_RAZONAMIENTO = {"scouting", "manager", "manager_consejo", "club_vendedor", "agente_jugador"}

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

# --- Estilo de los mensajes del Selling Club Agent
# Probabilidad de que un mensaje incluya un argumento "humano" (por ejemplo, su peso en el vestuario).
# Es un recurso ocasional; para eliminarlo basta con poner 0.
PROB_ARGUMENTO_HUMANO = 0.15

# --- Tiempos y rondas
MAX_RONDAS_CLUB = 5
DIAS_RESPUESTA_MIN = 1              # la respuesta a la oferta inicial nunca llega el mismo día
DIAS_POR_NEGOCIACION = 1            # cada negociación (club o jugador) consume este número de días
CONCESION_RESPALDO = 2.0            # forma de la regla de respaldo: >1 concede poco al inicio y más al final

# ======================================================================
# NEGOCIACIÓN CON EL JUGADOR (Paso 15)
# ======================================================================
# --- Salario: es privado; el comprador ve un intervalo que contiene el salario real
INTERVALO_SALARIO = (0.75, 1.25)          # extremos posibles del intervalo para la mayoría
INTERVALO_SALARIO_ESTRELLA = (0.90, 1.10) # las estrellas tienen sueldos más conocidos
REPUTACION_ESTRELLA = 4                   # es estrella con reputación internacional >= esto ...
RATING_ESTRELLA = 85                      # ... o con rating >= esto

# --- Exigencia salarial mínima = salario actual x factores (información privada del jugador)
PESO_CAMBIO_DE_CLUB = 1.00                # prima por cambiar de club (1 = no afecta)
PESO_BAJAR_NIVEL = 0.10                   # +10 % por cada nivel que baja el club comprador
PESO_PIERDE_EUROPA = 1.15                 # juega competición europea y el comprador no
PESO_GANA_EUROPA = 0.95                   # el comprador juega competición europea y su club no
PESO_ROTACION = 0.90                      # tendría rol de rotación en el club comprador
PESO_ESTRELLA = 1.25
PESO_AGENCIA_GRANDE = 1.05
N_AGENCIAS_GRANDES = 10                   # las agencias con más jugadores en la base
FACTOR_PEDIDO_JUGADOR = 1.20              # exigencia inicial = mínimo x este factor

# --- Años de contrato preferidos (rango sin penalización) y castigo por salirse
NIVEL_CLUB_GRANDE = 7                     # un club comprador con nivel >= esto es "grande"
ANIOS_JOVEN_CLUB_GRANDE = (4, 5)          # menores de EDAD_JOVEN que van a un club grande
ANIOS_JOVEN_CLUB_PEQUENO = (2, 3)         # menores de EDAD_JOVEN que van a un club no grande
ANIOS_ADULTO = (3, 4)                     # entre EDAD_JOVEN y EDAD_VETERANO
ANIOS_VETERANO = (3, 4)                   # desde EDAD_VETERANO: buscan seguridad
PENALIZACION_POR_ANIO = 0.05              # +5 % de salario exigido por cada año fuera del rango
MAX_ANIOS_CONTRATO = 6
VALOR_ANIO_OPCIONAL = 0.5                 # un año opcional (decide el club) vale medio año para el jugador

# --- Bonos (montos anuales): probabilidad de cumplirlos según la posición
TIPOS_BONO = ["goles", "asistencias", "partidos", "porterias_a_cero", "titulos", "clasificacion_europea"]
PROB_BONO = {
    #                 POR   DFC   LAT   MED   EXT   DEL
    "goles":        [0.00, 0.10, 0.10, 0.30, 0.45, 0.60],
    "asistencias":  [0.00, 0.10, 0.35, 0.45, 0.50, 0.40],
    "partidos":     [0.60, 0.60, 0.60, 0.60, 0.60, 0.60],
    "porterias_a_cero": [0.40, 0.35, 0.30, 0.05, 0.00, 0.00],
    "titulos":      [0.20, 0.20, 0.20, 0.20, 0.20, 0.20],
    "clasificacion_europea": [0.35, 0.35, 0.35, 0.35, 0.35, 0.35],
}
ORDEN_POSICIONES_BONO = ["POR", "DFC", "LAT", "MED", "EXT", "DEL"]

# --- Rondas, paciencia y plazos
MAX_RONDAS_JUGADOR = 4
UMBRAL_RUPTURA_JUGADOR = 0.60             # rompe si la oferta vale menos que esto x su mínimo
UMBRAL_RUPTURA_ESTRELLA = 0.75
CONCESION_JUGADOR = 1.5                   # forma de la regla de respaldo (más alto = cede más lento)
CONCESION_ESTRELLA = 3.0
DIAS_PLAZO_JUGADOR = 5                    # días para empezar a negociar con el jugador tras el acuerdo con el club
