from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Evento:
    """Lo que un agente avisa mientras trabaja, para que la interfaz lo muestre.

    Tipos:
    - `pensando`: el agente va a consultar al modelo (una vez por iteración).
    - `tool_call`: el modelo pidió una herramienta; datos `nombre` y `argumentos` (JSON crudo).
    - `tool_result`: terminó la herramienta; datos `nombre` y `error` (None si salió bien).
    """

    tipo: str
    agente: str
    datos: dict = field(default_factory=dict)


OnEvento = Callable[[Evento], None]
