# leo-ai

Agente de IA por consola (**Betito Bot**) para monitoreo agrícola / invernadero.
Un LLM servido por Groq, con tool-calling, consulta las lecturas de sensores
guardadas en MongoDB y ayuda a tomar decisiones sobre los cultivos.

Hoy hay dos agentes:

| Agente | Qué responde |
|---|---|
| `monitoreo` (por defecto) | Lecturas recientes por cultivo y recomendaciones generales. |
| `sensores` | Salud de los sensores: fallas, sensores sin reportar, nivel de depósitos, historial, DPV y riesgo de botrytis. |

Todavía no hay hardware: los datos del agente de sensores salen de un simulador.
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

```bash
python main.py
```

Escribe tu consulta (por ejemplo, "¿cómo está el tomate?" o "¿hay algún sensor
con falla?"). Mientras el agente trabaja se ve un spinner y una línea por cada
herramienta que consulta; al final, la respuesta con el nombre del agente que
la dio. La barra inferior muestra el agente y el modelo en uso.

- `/ayuda`, `/agentes`, `/limpiar` (borra la memoria de los agentes y la
  pantalla), `/salir`.
- `@sensores ...` o `@monitoreo ...` al inicio fuerza qué agente responde.
- Tab autocompleta comandos y agentes, Alt+Enter hace salto de línea, las
  flechas arriba/abajo recorren el historial (se guarda en
  `~/.leo_ai_historial`), Ctrl+C cancela la respuesta en curso y Ctrl+D (o
  `exit` / `salir`) termina la sesión.

### Cómo se elige el agente

Sin `@mención`, el ruteo es por palabras clave y no usa el LLM: los mensajes
que hablan de sensores, fallas, calibración, depósitos, nivel, CO2, lux, pH,
EC, DPV o botrytis van a `sensores`; todo lo demás va a `monitoreo`.

Cada agente guarda su propio historial (los últimos 20 mensajes) y el ruteo se
decide en cada mensaje. Por eso una pregunta de seguimiento sin palabras clave
la responde `monitoreo`, que no vio la conversación con `sensores`; para
continuar con el mismo agente, empieza el mensaje con `@sensores`.

## Uso con Docker

`docker-compose.yml` levanta el agente junto a un MongoDB local, con las
colecciones ya creadas por `mongo-init/init-mongo.js` y una lectura de ejemplo
(cultivo "Tomate") para el agente `monitoreo`.

1. Copia `.env.example` a `.env` y completa al menos `API_KEY_GROQ`. Compose
   sobreescribe `MONGO_URI`, `MONGO_DB_NAME` y `MONGO_COLLECTION_LECTURAS`
   para apuntar al Mongo del contenedor.
2. Levanta los servicios:

   ```bash
   docker compose up --build
   ```

   El CLI queda interactivo en la terminal (usa `docker attach` si lo corriste
   en background).

`init-mongo.js` solo corre al crear el volumen. Si cambias el esquema, recrea
el volumen con `docker compose down -v`.

Para conectarte a tu MongoDB Atlas desde el contenedor, corre solo la imagen
de la app sin levantar el servicio `mongo`:

```bash
docker build -t leo-ai .
docker run -it --rm --env-file .env leo-ai
```

## Datos simulados

El agente `sensores` necesita lecturas en `lecturas_sensores`. El simulador las
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

## Pruebas

```bash
pytest                                                    # toda la suite
pytest tests/test_validacion.py::test_ph_fuera_de_rango   # una prueba
pytest -k falla                                           # por nombre
```

No necesitan Mongo ni API key de Groq: usan `mongomock` y un cliente LLM falso.
La imagen Docker solo instala `requirements.txt`, así que las pruebas se corren
en el host.

## Estructura del repo

```
betito_bot/
  agents/         # un módulo por agente: system prompt, esquema de tools y registro
  llm/            # construcción del cliente del LLM (Groq)
  memory/         # memoria de conversación (historial por agente)
  orchestrator/   # enruta cada mensaje al agente correspondiente
  sensores/       # catálogo, reglas de validación y simulador
  tools/          # herramientas por dominio, de solo lectura sobre Mongo
  cli.py          # interfaz de consola (prompt_toolkit + Rich)
docs/             # contexto del proyecto y de los sensores
mongo-init/       # colecciones, esquemas e índices del Mongo local
tests/
main.py           # entrypoint
```

Un mensaje recorre `main.py` → `cli.py` → `Orchestrator.handle()` →
`agente.respond()` → bucle de tool-calling contra Groq → métodos de una clase
`*Tools` que leen Mongo.

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

### Colecciones

| Colección (default) | Quién la usa |
|---|---|
| `Mediciones_Sensores` (`LEO_AI` en compose) | Agente `monitoreo`; esquema estricto. |
| `lecturas_sensores` | Agente `sensores` y simulador; cada sensor publica solo sus variables. |
| `sensores` | Catálogo; `sensor_id` único. |

`fecha_hora` se guarda siempre en UTC sin zona horaria.

### Agregar un agente

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
