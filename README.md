# leo-ai

Agente de IA (**Betito Bot**) para monitoreo agrícola / invernadero. Un LLM
servido por Groq, orquestado con LangChain (`ChatGroq` + tool-calling),
consulta las lecturas de sensores guardadas en MongoDB y ayuda a tomar
decisiones sobre los cultivos. Se usa como microservicio FastAPI
(`POST /chat`) o desde la terminal.

**Instalación como microservicio:** [`docs/microservicio.md`](docs/microservicio.md).

Hoy hay tres agentes:

| Agente | Qué responde |
|---|---|
| `monitoreo` (por defecto) | Lecturas recientes por cultivo y recomendaciones generales. |
| `sensores` | Salud de los sensores: fallas, sensores sin reportar, nivel de depósitos, historial, DPV y riesgo de botrytis. |
| `riego` | Análisis de riego: ciclos reconstruidos (duración y frecuencia), cuánto sube la humedad de suelo tras cada uno, sobre-riego y riegos sin efecto. |

Todavía no hay hardware: los datos de los agentes de sensores y de riego salen de un simulador.
El contexto del proyecto (sensores elegidos, rangos, plan de arranque y
pendientes) está en [`docs/sensores.md`](docs/sensores.md).

## Requisitos

- Python 3.10 o superior (la imagen Docker usa 3.12).
- Una API key de [Groq](https://console.groq.com/).
- MongoDB: Atlas, o el contenedor local que levanta `docker-compose.yml`.

## Instalación

```bash
pip install -r requirements.txt                              # solo para usar el agente
pip install -r requirements.txt -r requirements-dev.txt      # además pytest y mongomock
```

Copia `.env.example` a `.env` y completa las variables:

| Variable | Default | Para qué |
|---|---|---|
| `API_KEY_GROQ` | — | API key de Groq. |
| `MONGO_URI` | — | Cadena de conexión a MongoDB. |
| `MONGO_DB_NAME` | — | Base de datos. |
| `MONGO_COLLECTION_LECTURAS` | `Mediciones_Sensores` | Lecturas que consulta `monitoreo`. |
| `MONGO_COLLECTION_SENSORES_LECTURAS` | `lecturas_sensores` | Lecturas que consulta `sensores` y que escribe el simulador. |
| `MONGO_COLLECTION_SENSORES_CATALOGO` | `sensores` | Catálogo de sensores. |
| `LLM_MODEL` | `openai/gpt-oss-20b` | Modelo de Groq que usan los agentes. |
| `TZ_OFFSET_HORAS` | `-6` | Desfase respecto a UTC para deducir la hora local. |

## Uso

### Microservicio (FastAPI)

```bash
uvicorn betito_bot.api:app --port 8000          # o: docker compose up -d --build
curl -X POST localhost:8000/chat -H "Content-Type: application/json" -d '{"mensaje": "¿Cómo está el tomate?"}'
```

Endpoints: `POST /chat`, `GET /agentes`, `POST /reset` y `GET /health`. La
documentación interactiva está en `/docs`. La guía completa está en
[`docs/microservicio.md`](docs/microservicio.md).

### Consola

```bash
python main.py            # consola (igual que python -m betito_bot.cli)
```

Escribe tu consulta (por ejemplo, "¿cómo está el tomate?" o "¿hay algún sensor
con falla?"). Mientras el agente trabaja se ve un spinner y una línea por cada
herramienta que consulta o agente en el que delega; al final, la respuesta con
el nombre del agente que la dio. La barra inferior muestra el agente y el
modelo en uso.

- `/ayuda`, `/agentes`, `/skills`, `/limpiar` (borra la memoria de los agentes
  y la pantalla), `/salir`.
- `/nombre-de-skill [@agente] petición` aplica una skill.
- `@sensores ...`, `@monitoreo ...` (o `@nombre` de un agente en Markdown) al
  inicio fuerza qué agente responde.
- Tab autocompleta comandos, skills y agentes, Alt+Enter hace salto de línea,
  las flechas arriba/abajo recorren el historial (se guarda en
  `~/.leo_ai_historial`), Ctrl+C cancela la respuesta en curso y Ctrl+D (o
  `exit` / `salir`) termina la sesión.

Las rutas de skills y agentes en Markdown se configuran en `config.toml`.

### Skills y agentes dedicados

- `betito_bot/skills/<nombre>/SKILL.md`: instrucciones reutilizables que se invocan con
  `/nombre [@agente] petición`. Ver `betito_bot/skills/README.md`. Ejemplos:
  `/reporte-diario` y `/diagnostico-sensor`.
- `betito_bot/agents/<nombre>.md`: agentes definidos por un prompt y una lista de tools
  existentes. Se usan con `@nombre`, y `monitoreo` también puede pasarles
  trabajo con la tool `delegate`. Ver `betito_bot/agents/README.md`.

### Cómo se elige el agente

Sin `@mención`, el ruteo es por palabras clave y no usa el LLM: los mensajes
que hablan de riego (riego, regar, sobre-riego, irrigación) van a `riego`; los
que hablan de sensores, fallas, calibración, depósitos, nivel, CO2, lux, pH,
EC, DPV o botrytis van a `sensores`; todo lo demás va a `monitoreo`. Si un
mensaje menciona riego y sensores, gana `riego`.

Cada agente guarda su propio historial (los últimos 20 mensajes) y el ruteo se
decide en cada mensaje. Por eso una pregunta de seguimiento sin palabras clave
la responde `monitoreo`, que no vio la conversación con `sensores`; para
continuar con el mismo agente, empieza el mensaje con `@sensores`.

`monitoreo` tiene además dos tools del orquestador: `delegate(agent, task)`,
para pasarle una tarea a otro agente (se ve en el panel lateral), y
`usar_skill(nombre)`, para leer una skill cuando la necesita.

## Uso con Docker

`docker-compose.yml` levanta el microservicio (`api`, puerto 8000) junto a un
MongoDB local, con las colecciones ya creadas por `mongo-init/init-mongo.js` y
una lectura de ejemplo (cultivo "Tomate") para el agente `monitoreo`.

1. Copia `.env.example` a `.env` y completa al menos `API_KEY_GROQ`. Compose
   sobreescribe `MONGO_URI`, `MONGO_DB_NAME` y `MONGO_COLLECTION_LECTURAS`
   para apuntar al Mongo del contenedor.
2. Levanta los servicios:

   ```bash
   docker compose up -d --build      # api + mongo
   docker compose run --rm consola   # la consola, con el mismo Mongo, con el mismo Mongo
   ```

`init-mongo.js` solo corre al crear el volumen. Si cambias el esquema, recrea
el volumen con `docker compose down -v`.

Para conectarte a tu MongoDB Atlas desde el contenedor, corre solo la imagen
de la app sin levantar el servicio `mongo`:

```bash
docker build -t leo-ai .
docker run --rm -p 8000:8000 --env-file .env leo-ai           # microservicio
docker run -it --rm --env-file .env leo-ai python main.py     # terminal
```

## Datos simulados

Los agentes `sensores` y `riego` necesitan lecturas en `lecturas_sensores`. El simulador las
genera (una por minuto y por sensor) y además siembra el catálogo:

```bash
docker compose up -d mongo
# en .env: MONGO_URI=mongodb://localhost:27017/ y MONGO_DB_NAME=LEO_AI
python -m betito_bot.sensores.simulador --limpiar --backfill 24                 # 24 h sanas
python -m betito_bot.sensores.simulador --limpiar --backfill 24 --falla ph_14 --falla sensor_mudo
python -m betito_bot.sensores.simulador --continuo                              # 1 lectura/min
```

El catálogo simulado tiene ocho sensores: tres SHT31 (temperatura y humedad del
aire), un SCD40 (CO2), un BH1750 (lux), una sonda de suelo Gemho 7 en 1, un
A02YYUW (nivel del depósito) y un DS18B20 (temperatura del agua), repartidos
entre "Parcela 1" (Fresa), "Parcela 2" (Jitomate) y "Depósitos".

`--falla` se puede repetir y solo afecta los últimos `--falla-min` minutos del
backfill (30 por defecto):

| Falla | Qué simula |
|---|---|
| `sensor_mudo` | Un SHT31 deja de reportar. |
| `ds18b20_85` | El DS18B20 entrega sus valores de error (85.0 y -127). |
| `nivel_0` | El depósito marca nivel 0. |
| `ph_14` | pH del suelo fuera de rango. |
| `co2_2500` | CO2 fuera de rango. |
| `lux_saturado` | El BH1750 satura en 65535. |
| `sht31_discrepante` | Dos SHT31 de la misma zona no coinciden. |
| `suelo_plano` | La humedad del suelo se queda fija (sensor trabado). Necesita `--falla-min 180` para que se detecte. |
| `sobre_riego` | La humedad del suelo sube 20 puntos: cada riego pasa del máximo de 75 %. |
| `riego_sin_efecto` | Se riega pero la humedad del suelo no sube. |

El simulador riega 10 minutos cada 4 horas. Para que el agente `riego` vea
riegos completos con `sobre_riego` o `riego_sin_efecto`, usa `--falla-min 480`
o más.

## Pruebas

```bash
pytest                                                    # toda la suite
pytest tests/test_validacion.py::test_ph_fuera_de_rango   # una prueba
pytest -k falla                                           # por nombre
```

No necesitan Mongo ni API key de Groq: usan `mongomock`, un chat model falso
de LangChain (`tests/fakes.py`) y `TestClient` de FastAPI para la API.
La imagen Docker solo instala `requirements.txt`, así que las pruebas se corren
en el host.

## Estructura del repo

```
betito_bot/
  agents/         # agentes: en Python (*_agent.py) o en Markdown (<nombre>.md: frontmatter + prompt)
  core/           # config, skills, agentes .md y frontmatter
  llm/            # construcción del chat model de LangChain (ChatGroq)
  memory/         # memoria de conversación (historial por agente)
  orchestrator/   # enruta cada mensaje al agente correspondiente
  sensores/       # catálogo, reglas de validación y simulador
  skills/         # skills: skills/<nombre>/SKILL.md
  tools/          # herramientas por dominio, de solo lectura sobre Mongo
  api.py          # microservicio FastAPI: /chat, /agentes, /reset, /health
  cli.py          # interfaz de consola (prompt_toolkit + Rich)
config.toml       # rutas de skills y agentes en Markdown
docs/             # contexto del proyecto y de los sensores
mongo-init/       # colecciones, esquemas e índices del Mongo local
tests/
main.py           # entrypoint de la consola
```

Un mensaje recorre `main.py` → `cli.py` → `Orchestrator.handle()` →
`agente.respond()` → bucle de tool-calling de LangChain (`ChatGroq.bind_tools`)
→ métodos de una clase `*Tools` que leen Mongo. Los `Evento` que emite el
agente (pensando, tool_call, tool_result y, al delegar, agente_inicio/agente_fin)
son lo único que la consola consume para mostrar el progreso. En la API,
`POST /chat` llama a `Orchestrator.handle()` igual y junta las tools usadas en
la respuesta.

### Agente de sensores

El principio de diseño es que el LLM no calcula ni valida nada: solo redacta lo
que devuelven funciones fijas de solo lectura.

- `betito_bot/tools/sensores_tools.py`: las herramientas `estado_sensores`,
  `ultimo_estado`, `historial`, `nivel_depositos`, `calcular_dpv` y
  `riesgo_botrytis`.
- `betito_bot/sensores/validacion.py`: las reglas (rangos, valores de error
  conocidos, valor plano, discrepancia entre SHT31 de la misma zona) y los
  cálculos agronómicos.
- `betito_bot/sensores/catalogo.py`: la lista de sensores, fuente única para el
  simulador y las pruebas.

### Agente de riego

Sigue el mismo principio: los ciclos y sus diagnósticos se calculan en código.

- `betito_bot/tools/riego_tools.py`: las herramientas `resumen_riego` y
  `ciclos_riego`. Leen las lecturas de los sensores de suelo que traen
  `riego_activo` junto a `humedad_suelo_pct`.
- `betito_bot/sensores/riego.py`: reconstruye los ciclos (rachas de
  `riego_activo`), mide la humedad antes y el pico hasta 30 min después, y
  clasifica cada ciclo. Los umbrales son constantes de ese módulo: un riego
  que sube la humedad menos de 2 puntos es "sin efecto"; uno cuyo pico pasa de
  75 %, o que empieza con el suelo ya en 70 % o más, es "sobre-riego".

### Colecciones

| Colección (default) | Quién la usa |
|---|---|
| `Mediciones_Sensores` (`LEO_AI` en compose) | Agente `monitoreo`; esquema estricto. |
| `lecturas_sensores` | Agentes `sensores` y `riego`, y simulador; cada sensor publica solo sus variables. |
| `sensores` | Catálogo; `sensor_id` único. |

`fecha_hora` se guarda siempre en UTC sin zona horaria.

### Agregar un agente

Lo más simple es un agente dedicado en `betito_bot/agents/<nombre>.md`, que reutiliza tools
ya existentes (ver `betito_bot/agents/README.md`). Si necesita tools nuevas:

1. Crea `betito_bot/agents/<nombre>_agent.py` con una clase que extienda
   `ToolAgent` (`betito_bot/agents/tool_agent.py`) y defina `name`,
   `descripcion`, prompt de sistema, esquema de tools y registro.
2. Si necesita herramientas propias, agrégalas en `betito_bot/tools/` como un
   módulo separado (una clase de tools por dominio). Las tools no deben hacer
   `print`: la interfaz ya muestra cada llamada.
3. Registra el agente en `betito_bot/orchestrator/router.py` y define ahí su
   criterio de ruteo. La clave en `Orchestrator.agents` es el nombre que se usa
   en la `@mención`.

## Licencia

[GPL-3.0](LICENSE).
