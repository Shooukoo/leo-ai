"""Microservicio FastAPI que expone el orquestador de agentes por HTTP.

    uvicorn betito_bot.api:app --host 0.0.0.0 --port 8000
    python -m betito_bot.api                # lo mismo, con API_HOST / API_PORT

La memoria vive en el proceso y es una por sesión: `/chat` devuelve un
identificador `sesion` que el cliente reenvía para continuar la conversación.
`POST /reset` borra una sesión o todas. Los mensajes se atienden de uno en uno
(`lock`) porque la memoria de los agentes no es segura para uso concurrente.

Si `BETITO_API_KEY` está definida, todo salvo `/health` exige el header
`X-API-Key`.
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from betito_bot.agents.eventos import Evento
from betito_bot.orchestrator.router import AgenteDesconocido, Orchestrator
from betito_bot.seguridad.reglas import MAX_MENSAJE

log = logging.getLogger(__name__)

SESION_PATRON = r"^[\w-]{1,64}$"
AVISO_SIN_CLAVE = "La API no pide clave: define BETITO_API_KEY para exigir el header X-API-Key."


class ChatPeticion(BaseModel):
    mensaje: str = Field(min_length=1, max_length=MAX_MENSAJE, description="Pregunta del usuario. Acepta `@agente` al inicio.")
    agente: str | None = Field(None, max_length=65, description="Fuerza un agente (equivale a escribir `@agente` en el mensaje).")
    sesion: str | None = Field(None, pattern=SESION_PATRON, description="Sesión a continuar; si falta se crea una nueva.")


class ResetPeticion(BaseModel):
    sesion: str | None = Field(None, pattern=SESION_PATRON, description="Sesión a borrar; si falta se borran todas.")


class Herramienta(BaseModel):
    agente: str
    nombre: str
    argumentos: str
    error: str | None = None


class ChatRespuesta(BaseModel):
    agente: str
    respuesta: str
    herramientas: list[Herramienta] = Field(description="Tools que llamaron los agentes, en orden.")
    sesion: str = Field(description="Identificador de la conversación; envíalo en el siguiente mensaje para continuarla.")
    bloqueado: str | None = Field(None, description="Motivo si el guardián rechazó el mensaje o la respuesta.")


def exigir_clave(x_api_key: str | None = Header(None)) -> None:
    """Si hay `BETITO_API_KEY`, la petición debe traerla en `X-API-Key`."""
    clave = os.getenv("BETITO_API_KEY")
    if clave and not secrets.compare_digest((x_api_key or "").encode(), clave.encode()):
        raise HTTPException(401, detail="Falta el header X-API-Key o no es válido.")


def _orquestador_por_defecto() -> tuple[Orchestrator | None, list[str]]:
    """Arma el orquestador real y devuelve los avisos de carga."""
    from betito_bot.core.config import cargar_config
    from betito_bot.core.sistema import construir_orquestador
    from betito_bot.llm.groq_client import build_client

    try:
        client = build_client()
    except Exception:  # p. ej. falta API_KEY_GROQ: el servicio arranca y /health lo reporta
        log.exception("No se pudo crear el cliente de Groq")
        return None, ["No se pudo crear el cliente de Groq. Revisa API_KEY_GROQ."]
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
        avisos = estado["avisos"] + ([] if os.getenv("BETITO_API_KEY") else [AVISO_SIN_CLAVE])
        return {"status": "ok" if listo else "degradado", "avisos": avisos}

    @app.get("/agentes", dependencies=[Depends(exigir_clave)])
    def agentes() -> list[dict]:
        return [{"nombre": n, "descripcion": a.descripcion} for n, a in _orq().agents.items()]

    @app.post("/chat", response_model=ChatRespuesta, dependencies=[Depends(exigir_clave)])
    def chat(peticion: ChatPeticion) -> ChatRespuesta:
        # `def` síncrono: FastAPI lo corre en su pool de hilos y no bloquea el event loop.
        orq = _orq()
        texto = f"@{peticion.agente.lstrip('@')} {peticion.mensaje}" if peticion.agente else peticion.mensaje
        sesion = peticion.sesion or uuid.uuid4().hex
        herramientas: list[Herramienta] = []
        bloqueos: list[str] = []

        def on_event(e: Evento) -> None:
            if e.tipo == "bloqueado":
                bloqueos.append(str(e.datos.get("motivo")))
            elif e.tipo == "tool_call":
                herramientas.append(Herramienta(agente=e.agente, nombre=e.datos["nombre"], argumentos=e.datos["argumentos"]))
            elif e.tipo == "tool_result" and e.datos.get("error"):
                for h in reversed(herramientas):
                    if h.nombre == e.datos["nombre"] and h.agente == e.agente:
                        h.error = str(e.datos["error"])
                        break

        with lock:
            try:
                respuesta = orq.handle(texto, on_event, sesion=sesion)
            except AgenteDesconocido:
                raise HTTPException(404, detail=f"No existe ese agente. Disponibles: {', '.join(orq.agents)}")
            except Exception:  # fallo del modelo o de la base: no tumba el servicio ni expone el detalle
                log.exception("Fallo al atender /chat")
                raise HTTPException(502, detail="No se pudo completar la consulta: falló el modelo o la base de datos.")
            agente = orq.ultimo_agente.name if orq.ultimo_agente else ""
        return ChatRespuesta(agente=agente, respuesta=respuesta, herramientas=herramientas, sesion=sesion,
                             bloqueado=bloqueos[-1] if bloqueos else None)

    @app.post("/reset", dependencies=[Depends(exigir_clave)])
    def reset(peticion: ResetPeticion | None = None) -> dict:
        with lock:
            _orq().reset(peticion.sesion if peticion else None)
        return {"ok": True}

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=os.getenv("API_HOST", "127.0.0.1"), port=int(os.getenv("API_PORT", "8000")))


if __name__ == "__main__":
    main()
