from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Evento:
    """Lo que un agente avisa mientras trabaja, para que la interfaz lo muestre.

    Tipos:
    - `pensando`: el agente va a consultar al modelo (una vez por iteración).
    - `tool_call`: el modelo pidió una herramienta; datos `nombre` y `argumentos` (JSON crudo).
    - `tool_result`: terminó la herramienta; datos `nombre`, `error` (None si salió bien) y `resultado`.
    - `agente_inicio` / `agente_fin`: el orquestador delegó una tarea a otro agente
      (`tool_call` de `delegate`); datos `tarea` en el inicio y `ok` en el fin.
    - `bloqueado`: el guardián rechazó el mensaje (`etapa="entrada"`) o la respuesta
      (`etapa="salida"`); datos `etapa` y `motivo`.
    """

    tipo: str
    agente: str
    datos: dict = field(default_factory=dict)


OnEvento = Callable[[Evento], None]
