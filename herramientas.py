from datos import buscar_jugadores, evaluar_encaje

HERRAMIENTAS_SCOUTING = [
    {
        "type": "function",
        "function": {
            "name": "buscar_jugadores",
            "description": "Busca jugadores por posición con filtros opcionales, ordenados por rating descendente. Cada resultado incluye su id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "posicion": {"type": "string", "description": "Código: POR, DFC, LAT, MED, EXT o DEL"},
                    "edad_max": {"type": "integer", "description": "Edad máxima"},
                    "valor_max": {"type": "number", "description": "Valor de mercado máximo, en millones de euros"},
                    "excluir_club": {"type": "string", "description": "Club a excluir de la búsqueda"},
                },
                "required": ["posicion"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evaluar_encaje",
            "description": "Evalúa qué tanto mejora un jugador a la plantilla del club: compara su rating con el mejor actual en esa posición y entrega edad, contrato y nivel de clubes.",
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