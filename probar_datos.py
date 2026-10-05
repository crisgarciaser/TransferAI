from datos import obtener_plantilla, obtener_resumen_club, buscar_jugadores

def mostrar(jugadores):
    for j in jugadores:
        print(f"{j['nombre']:<20} {j['posicion']}  {j['edad']} años  "
              f"{j['club']:<18} valor={j['valor_mercado']}  rating={j['rating']}")

club = "Deportivo Mirador"

print(obtener_resumen_club(club))
print()
mostrar(obtener_plantilla(club))
print()
mostrar(buscar_jugadores("DFC", edad_max=28, valor_max=20, excluir_club=club))