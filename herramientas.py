from datos import buscar_jugadores, evaluar_encaje

HERRAMIENTAS_SCOUTING = [
    {
        "type": "function",
        "function": {
            "name": "buscar_jugadores",
            "description": "Busca jugadores por posición con filtros opcionales, ordenados por rating (o por potencial) descendente. Cada resultado incluye su id, rating y potencial.",
            "parameters": {
                "type": "object",
                "properties": {
                    "posicion": {"type": "string", "description": "Código: POR, DFC, LAT, MED, EXT o DEL"},
                    "edad_max": {"type": "integer", "description": "Edad máxima"},
                    "valor_max": {"type": "number", "description": "Valor de mercado máximo, en millones de euros"},
                    "excluir_club": {"type": "string", "description": "Club a excluir de la búsqueda"},
                    "edad_min": {"type": "integer", "description": "Edad mínima; útil para pedir veteranos (por ejemplo 30)"},
                    "rating_min": {"type": "integer", "description": "Rating mínimo (calidad actual)"},
                    "rating_max": {"type": "integer", "description": "Rating máximo (calidad actual)"},
                    "potencial_min": {"type": "integer", "description": "Potencial mínimo (calidad que puede alcanzar)"},
                    "ordenar_por": {"type": "string", "enum": ["rating", "potencial"], "description": "Criterio de orden descendente. Usa \"potencial\" para buscar promesas; por defecto \"rating\""},
                },
                "required": ["posicion"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evaluar_encaje",
            "description": "Evalúa qué tanto aporta un jugador a la plantilla del club: compara su rating con el mejor actual en esa posición y entrega edad, contrato y nivel de clubes. Incluye el potencial del jugador y tipo_de_fichaje, que puede ser mejora_inmediata, sucesor_joven, promesa o no_aporta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_jugador": {"type": "integer", "description": "Id del jugador, tal como lo entrega buscar_jugadores"},
                    "club": {"type": "string", "description": "Nombre exacto del club del usuario"},
                },
                "required": ["id_jugador", "club"],
            },
        },
    },
]

FUNCIONES_SCOUTING = {
    "buscar_jugadores": buscar_jugadores,
    "evaluar_encaje": evaluar_encaje,
}