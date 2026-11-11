
# TransferAI 

*Curso Agentic AI — Universidad de Los Andes. Autor: Cristian García S.*

1. Clona el repositorio e instala las dependencias (requiere Python 3.10 o superior):

   ```bash
   git clone https://github.com/crisgarciaser/TransferAI.git
   cd TransferAI
   pip install -r requirements.txt
   ```

2. Copia la plantilla de variables de entorno:

   ```bash
   copy .env.example .env      # Windows
   cp .env.example .env        # macOS / Linux
   ```

3. Abre `.env` y completa estas tres variables:

   | Variable | Qué poner |
   |---|---|
   | `QWEN_API_KEY` | Tu clave de API. |
   | `QWEN_BASE_URL` | URL base de un endpoint **compatible con el formato de OpenAI**; suele terminar en `/compatible-mode/v1`. |
   | `QWEN_MODEL` | Nombre exacto de un modelo con soporte de **llamadas a herramientas** (*tool calling*). |

   Estos valores se obtienen en la consola de tu proveedor (el proyecto se probó con Qwen en Alibaba Cloud Model Studio). Ejemplo del formato:

   ```
   QWEN_API_KEY=sk-xxxxxxxxxxxxxxxx
   QWEN_BASE_URL=https://tu-endpoint/compatible-mode/v1
   QWEN_MODEL=nombre-del-modelo
   ```

## Uso

Hay dos formas de jugar, ambas sobre el mismo grafo:

```bash
python web.py      # página web: abre http://localhost:5000 en el navegador
python grafo.py    # terminal
```

Primero se elige el club: el nombre completo o parcial, sin importar mayúsculas ni tildes (por ejemplo, `fiorentina` o `atletico`). Luego se llega al **centro de mando**, al que se vuelve después de cada acción hasta cerrar el mercado o llegar al día 30:

| Opción | Qué hace |
|---|---|
| `1` Ver plantilla | Plantilla actual por posición, incluidos los fichajes de la ventana. |
| `2` Estado del club | Día, presupuesto, margen salarial, operaciones y negociaciones abiertas. |
| `3` Bandeja | Respuestas de los clubes y ofertas recibidas. |
| `4` Buscar refuerzos | Diagnóstico del Manager, scouting, análisis financiero y elección de objetivos. |
| `5` Fichajes | Primer contacto y negociación con el club vendedor y luego con el jugador. |
| `6` Ventas | Poner jugadores a la venta y responder las ofertas que llegan. |
| `7` Avanzar días | `7` avanza un día; `7 5`, cinco. Llegan respuestas y ofertas, y vencen plazos. |
| `8` Cerrar mercado | Termina la ventana y muestra el resumen final. |

En **Buscar refuerzos** se confirman las posiciones a reforzar con códigos o nombres (`MED`, `DFC, LAT`, `defensas`) y luego se elige un candidato por su `id`, se pide otra ronda con una indicación (`nueva: más jóvenes`, `nueva: zurdos`, `nueva: promesas con alto potencial`) o se escribe `salir`. Hay un máximo de **3 rondas** por búsqueda.

En **Fichajes** y **Ventas** los mensajes se escriben en lenguaje natural, como a un club real (por ejemplo, `Ofrecemos 30 millones más 5 en variables, en dos cuotas`). Se puede mostrar interés sin cifras, ofertar, pagar la cláusula, aceptar las condiciones del otro o retirarse, y pedir consejo con `consejo m` (Manager) o `consejo f` (Financial). Si una oferta es ambigua, el sistema pide confirmarla (`s/n`).

En la terminal, cada línea `ACTUAR` que aparece durante el scouting es una llamada del agente a una de sus herramientas. Cada partida hace varias llamadas al modelo y consume cuota de la API. Cada sesión queda registrada en `logs/sesion_<fecha>.jsonl`.

## Estructura del repositorio

| Archivo | Contenido |
|---|---|
| `grafo.py` | Estado compartido, nodos de la ventana, pausas humanas, construcción del grafo y punto de entrada de la terminal. |
| `config.py` | Parámetros de diseño: límites, ponderaciones y umbrales. |
| `llm.py` | Conexión con el modelo, control del razonamiento, ciclo con herramientas y reparación de JSON. |
| `herramientas.py` | Esquemas de las herramientas del Scouting Agent; oculta el salario real. |
| `datos.py` | Lectura de los CSV, búsqueda de jugadores, evaluación de encaje, viabilidad e intervalo salarial. |
| `tactica.py` | Identidad táctica del club, perfil del jugador y encaje táctico. |
| `ventana.py` | Calendario, bandeja y lectura de comandos del centro de mando. |
| `registro.py` | Emisión de eventos y escritura del log de cada sesión. |
| `agentes/` | Manager, Scouting & Tactical, Financial, agente de club y Player Agent. |
| `negociacion/` | Intérprete, reglas del árbitro y nodos de compra, contrato y venta. |
| `interfaz_terminal.py` | Interfaz de terminal. |
| `web.py` y `web/` | Servidor Flask y página web (HTML, CSS y JavaScript). |
| `filtrar_originales.py` | Filtra los archivos originales de Kaggle y genera `datos_fuente/`. |
| `convertir_datos.py` | Construye `datos_reales/` a partir de `datos_fuente/`. |
| `datos_fuente/` | CSV filtrados de EA Sports FC 24 y Transfermarkt. |
| `datos_reales/` | Base de datos usada: 96 clubes y 2.808 jugadores de las cinco grandes ligas (temporada 2023/24). |
| `.env.example` | Plantilla de variables de entorno. |
| `requirements.txt` | Dependencias. |


## Datos

`datos_reales/` ya viene incluida, así que no hace falta descargar nada. Combina el dataset [EA Sports FC 24 Complete Player Dataset](https://www.kaggle.com/datasets/stefanoleone992/ea-sports-fc-24-complete-player-dataset) con [Football Data from Transfermarkt](https://www.kaggle.com/datasets/mexwell/football-data-from-transfermarkt) (Kaggle), de donde proviene el valor de mercado del 79 % de los jugadores.

Para regenerarla basta con ejecutar `python convertir_datos.py`, que usa los archivos ya incluidos en `datos_fuente/`. Para reconstruir también `datos_fuente/` desde cero:

1. Descarga los archivos completos de ambos datasets y colócalos en `datos_originales/` (los de Transfermarkt en `datos_originales/transfermarkt/`).
2. Ejecuta `python filtrar_originales.py` y luego `python convertir_datos.py`.

El presupuesto de fichajes, el bono por competición europea y el tope salarial **no existen en los datos** y son estimaciones de diseño (editables al inicio de `convertir_datos.py`). Las reglas del simulador (umbrales de edad y rating, viabilidad financiera, negociación y ventas) se editan en `config.py`.
