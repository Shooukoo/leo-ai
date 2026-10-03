"""Microservicio FastAPI que expone el orquestador de agentes por HTTP.

    uvicorn betito_bot.api:app --host 0.0.0.0 --port 8000
    python -m betito_bot.api                # lo mismo, con API_HOST / API_PORT

La memoria de cada agente vive en el proceso y la comparten todos los clientes;
`POST /reset` la borra. Los mensajes se atienden de uno en uno (`_lock`) porque
la memoria de los agentes no es segura para uso concurrente.
"""

from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from betito_bot.agents.eventos import Evento
from betito_bot.orchestrator.router import AgenteDesconocido, Orchestrator


class ChatPeticion(BaseModel):
    mensaje: str = Field(min_length=1, description="Pregunta del usuario. Acepta `@agente` al inicio.")
    agente: str | None = Field(None, description="Fuerza un agente (equivale a escribir `@agente` en el mensaje).")


class Herramienta(BaseModel):
    agente: str
    nombre: str
    argumentos: str
    error: str | None = None


class ChatRespuesta(BaseModel):
    agente: str
    respuesta: str
    herramientas: list[Herramienta] = Field(description="Tools que llamaron los agentes, en orden.")


def _orquestador_por_defecto() -> tuple[Orchestrator | None, list[str]]:
    """Arma el orquestador real y devuelve los avisos de carga."""
    from betito_bot.core.config import cargar_config
    from betito_bot.core.sistema import construir_orquestador
    from betito_bot.llm.groq_client import build_client

    try:
        client = build_client()
    except Exception as e:  # p. ej. falta API_KEY_GROQ: el servicio arranca y /health lo reporta
        return None, [f"No se pudo crear el cliente de Groq ({e}). Revisa API_KEY_GROQ."]
    return construir_orquestador(cargar_config(), client)


def create_app(orchestrator: Orchestrator | None = None) -> FastAPI:
    """Crea la app; sin `orchestrator` arma el real al arrancar (las pruebas pasan uno)."""
    estado: dict = {"orchestrator": orchestrator, "avisos": []}
    lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if estado["orchestrator"] is None:
            estado["orchestrator"], estado["avisos"] = _orquestador_por_defecto()
        yield

    app = FastAPI(
        title="BETITO BOT",
        description="Agente conversacional de monitoreo agrícola (LangChain + Groq).",
        version="0.1.0",
        lifespan=lifespan,
    )

    def _orq() -> Orchestrator:
        if estado["orchestrator"] is None:
            raise HTTPException(503, detail=" ".join(estado["avisos"]) or "Orquestador no disponible.")
        return estado["orchestrator"]

    @app.get("/health")
    def health() -> dict:
        listo = estado["orchestrator"] is not None
        return {"status": "ok" if listo else "degradado", "avisos": estado["avisos"]}

    @app.get("/agentes")
    def agentes() -> list[dict]:
        return [{"nombre": n, "descripcion": a.descripcion} for n, a in _orq().agents.items()]

    @app.post("/chat", response_model=ChatRespuesta)
    def chat(peticion: ChatPeticion) -> ChatRespuesta:
        # `def` síncrono: FastAPI lo corre en su pool de hilos y no bloquea el event loop.
        orq = _orq()
        texto = f"@{peticion.agente.lstrip('@')} {peticion.mensaje}" if peticion.agente else peticion.mensaje
        herramientas: list[Herramienta] = []

        def on_event(e: Evento) -> None:
            if e.tipo == "tool_call":
                herramientas.append(Herramienta(agente=e.agente, nombre=e.datos["nombre"], argumentos=e.datos["argumentos"]))
            elif e.tipo == "tool_result" and e.datos.get("error"):
                for h in reversed(herramientas):
                    if h.nombre == e.datos["nombre"] and h.agente == e.agente:
                        h.error = str(e.datos["error"])
                        break

        with lock:
            try:
                respuesta = orq.handle(texto, on_event)
            except AgenteDesconocido as e:
                raise HTTPException(404, detail=f"No existe el agente {e}. Disponibles: {', '.join(orq.agents)}")
            except Exception as e:  # fallo del modelo o de la base: no tumba el servicio
                raise HTTPException(502, detail=f"{type(e).__name__}: {e}")
            agente = orq.ultimo_agente.name if orq.ultimo_agente else ""
        return ChatRespuesta(agente=agente, respuesta=respuesta, herramientas=herramientas)

    @app.post("/reset")
    def reset() -> dict:
        with lock:
            _orq().reset()
        return {"ok": True}

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=os.getenv("API_HOST", "127.0.0.1"), port=int(os.getenv("API_PORT", "8000")))


if __name__ == "__main__":
    main()
