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
