# Guía de instalación: el agente como microservicio

Betito Bot expone sus agentes por HTTP con FastAPI (`betito_bot/api.py`). El
endpoint principal es `POST /chat`: recibe una pregunta, el orquestador la
envía al agente que corresponde y el agente (un bucle de tool-calling de
LangChain con `ChatGroq`) consulta MongoDB y responde.

```
cliente HTTP ──POST /chat──▶ FastAPI ──▶ Orchestrator ──▶ ToolAgent (LangChain + ChatGroq)
                                                              │
                                                              └─▶ tools de solo lectura ──▶ MongoDB
```

## 1. Requisitos

- Una API key de [Groq](https://console.groq.com/keys).
- **Con Docker (recomendado):** Docker 24+ con Docker Compose v2.
- **Sin Docker:** Python 3.10 o superior y un MongoDB (Atlas o local).

## 2. Obtener el código

```bash
git clone https://github.com/Shooukoo/leo-ai.git
cd leo-ai
cp .env.example .env
```

Edita `.env` y llena al menos `API_KEY_GROQ`. La tabla completa de variables
está en el [README](../README.md#instalación).

## 3a. Despliegue local con Docker

```bash
docker compose up -d --build
```

Esto levanta dos contenedores:

| Servicio | Puerto | Qué es |
|---|---|---|
| `api` | 8000 | El microservicio FastAPI (uvicorn). |
| `mongo` | 27017 | MongoDB 7, con colecciones e índices creados por `mongo-init/init-mongo.js` y una lectura de ejemplo del cultivo "Tomate". |

Compose apunta la API al Mongo del contenedor. Para eso sobreescribe
`MONGO_URI`, `MONGO_DB_NAME` y `MONGO_COLLECTION_LECTURAS` del `.env`.

Para comprobar que la API arrancó:

```bash
docker compose ps        # api debe quedar "healthy"
docker compose logs -f api
```

Para cargar datos simulados de sensores (lo necesita el agente `sensores`):

```bash
docker compose exec api python -m betito_bot.sensores.simulador --limpiar --backfill 24
```

Para detener los servicios:

```bash
docker compose down        # conserva los datos
docker compose down -v     # borra también el volumen de Mongo
```

Si ya tienes ocupados los puertos 8000 o 27017, cambia el lado izquierdo de
`ports` en `docker-compose.yml` (por ejemplo, `"18000:8000"`).

## 3b. Despliegue local sin Docker

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

En `.env`, apunta `MONGO_URI` y `MONGO_DB_NAME` a tu Mongo. Para usar el Mongo
del contenedor sin la API, corre `docker compose up -d mongo` y pon
`MONGO_URI=mongodb://localhost:27017/` y `MONGO_DB_NAME=LEO_AI`.

```bash
uvicorn betito_bot.api:app --host 0.0.0.0 --port 8000 --reload
# o: python -m betito_bot.api   (usa API_HOST, default 127.0.0.1, y API_PORT, default 8000)
```

## 4. Probar el endpoint `/chat`

La documentación interactiva (Swagger) está en <http://localhost:8000/docs>.

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"mensaje": "¿Cómo está el tomate?"}'
```

```json
{
  "agente": "monitoreo",
  "respuesta": "**Estado del tomate** ...",
  "herramientas": [
    {"agente": "monitoreo", "nombre": "get_ultimas_lecturas",
     "argumentos": "{\"cultivo\": \"tomate\", \"minutos\": 120}", "error": null}
  ]
}
```

Para forzar un agente, usa el campo `agente` o escribe `@nombre` al inicio del
mensaje:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"mensaje": "¿hay sensores con falla?", "agente": "sensores"}'
```

## 5. Referencia de la API

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/chat` | Body `{"mensaje": str, "agente": str opcional}`. Devuelve `agente`, `respuesta` y `herramientas` (las tools que llamaron los agentes, en orden). |
| `GET` | `/agentes` | Lista los agentes disponibles, con su descripción. |
| `POST` | `/reset` | Borra la memoria de conversación de todos los agentes. |
| `GET` | `/health` | `{"status": "ok" \| "degradado", "avisos": [...]}`. Es `degradado`, por ejemplo, si falta `API_KEY_GROQ`. |

Códigos de error de `/chat`:

| Código | Cuándo |
|---|---|
| `404` | El agente pedido no existe. |
| `422` | Body inválido (por ejemplo, `mensaje` vacío). |
| `502` | Falló el modelo o la base de datos. El detalle viene en `detail`. |
| `503` | El servicio arrancó sin cliente de Groq (revisa `API_KEY_GROQ`). |

## 6. Notas

- Cada agente guarda en memoria los últimos 20 mensajes. Esa memoria es del
  proceso y la comparten todos los clientes de la API. `POST /reset` la borra.
- La API atiende un mensaje a la vez, porque la memoria de los agentes no es
  segura para uso concurrente.
- La interfaz de terminal sigue disponible: `docker compose run --rm consola` o
  `python main.py`.
- Las pruebas de la API (`tests/test_api.py`) usan `TestClient` y un chat
  model falso de LangChain, así que no necesitan Groq ni Mongo:
  `pip install -r requirements-dev.txt && pytest tests/test_api.py`.
