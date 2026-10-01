# leo-ai

Agente de IA para monitoreo agrícola. Usa un LLM (vía Groq) con tool-calling
para consultar lecturas de sensores (temperatura, humedad de suelo/aire,
riego) almacenadas en MongoDB y ayudar a tomar decisiones sobre los cultivos.

El proyecto está organizado para crecer hacia un **sistema multiagente**:
hoy existe un único agente de monitoreo, pero la estructura permite sumar
agentes nuevos (riego, alertas, clima, etc.) sin reescribir lo existente.

## Estructura del repo

```
betito_bot/
  llm/            # construcción del cliente del LLM (Groq)
  memory/         # memoria de conversación (historial por agente)
  tools/          # implementación de herramientas por dominio (Mongo, etc.)
  agents/         # un módulo por agente: su system prompt, sus tools y su lógica
  orchestrator/   # enruta cada mensaje del usuario al agente correspondiente
  cli.py          # loop de conversación por consola
main.py           # entrypoint
```

Convenciones para agregar un agente nuevo:

1. Crear `betito_bot/agents/<nombre>_agent.py` con una clase que extienda
   `BaseAgent` (`betito_bot/agents/base.py`) e implemente `respond(user_text)`.
2. Si necesita herramientas propias, agregarlas en `betito_bot/tools/` como un
   módulo separado (una clase de tools por dominio).
3. Registrar el agente en `betito_bot/orchestrator/router.py` y definir ahí el
   criterio de enrutamiento (por intención, palabra clave, agente por
   defecto, etc.).

## Configuración

1. Copia `.env.example` a `.env` y completa las variables:
   - `API_KEY_GROQ`: API key de Groq.
   - `MONGO_URI`: cadena de conexión a MongoDB Atlas.
   - `MONGO_DB_NAME`: nombre de la base de datos.
2. Instala las dependencias:

   ```bash
   pip install -r requirements.txt
   ```

## Uso

```bash
python main.py
```

Escribe tu consulta sobre un cultivo (por ejemplo, "¿cómo está el tomate?").
Escribe `exit` o `salir` para terminar.

## Uso con Docker

Para desarrollo local, `docker-compose.yml` levanta el agente junto a un
MongoDB local (en vez de Atlas), con la colección `LEO_AI` creada a partir
del mismo `$jsonSchema` usado en Atlas y una lectura de ejemplo precargada
(ver `mongo-init/init-mongo.js`).

1. Copia `.env.example` a `.env` y completa al menos `API_KEY_GROQ` (la
   variable `MONGO_URI` se sobreescribe automáticamente para apuntar al
   Mongo del contenedor).
2. Levanta los servicios:

   ```bash
   docker compose up --build
   ```

   El CLI queda interactivo en la terminal (usa `docker attach` si lo
   corriste en background, o simplemente dejá la consola en foreground).

Si en cambio querés conectarte a tu MongoDB Atlas real desde el contenedor,
corré solo la imagen de la app sin levantar el servicio `mongo`:

```bash
docker build -t leo-ai .
docker run -it --rm --env-file .env leo-ai
```

## Agente de sensores

El agente `sensores` (`betito_bot/agents/sensores_agent.py`) responde sobre la salud de los sensores del invernadero usando solo funciones fijas (`betito_bot/tools/sensores_tools.py`): `estado_sensores`, `ultimo_estado`, `historial`, `nivel_depositos`, `calcular_dpv` y `riesgo_botrytis`. Las reglas de validación viven en `betito_bot/sensores/validacion.py`. El `Orchestrator` lo elige por palabras clave (sensor, falla, depósito, nivel, CO2, lux, pH, EC...); el resto va a `monitoreo`.

Como todavía no hay hardware, se alimenta con datos simulados:

```bash
docker compose up -d mongo
# en el .env local apunta MONGO_URI a mongodb://localhost:27017/ y MONGO_DB_NAME=LEO_AI
python -m betito_bot.sensores.simulador --limpiar --backfill 24                 # 24 h sanas
python -m betito_bot.sensores.simulador --limpiar --backfill 24 --falla ph_14 --falla sensor_mudo
python -m betito_bot.sensores.simulador --continuo                              # 1 lectura/min
```

Fallas disponibles: `sensor_mudo`, `ds18b20_85`, `nivel_0`, `ph_14`, `co2_2500`, `lux_saturado`, `sht31_discrepante`, `suelo_plano` (esta última necesita `--falla-min 180`). Las colecciones nuevas (`lecturas_sensores`, `sensores`) se crean en `mongo-init/init-mongo.js` (solo al crear el volumen; con un volumen existente, ejecuta `docker compose down -v`) y el simulador siembra el catálogo.

Pruebas: `pip install -r requirements-dev.txt && pytest`.

Más contexto, hallazgos y vacíos abiertos en [`docs/sensores.md`](docs/sensores.md).
