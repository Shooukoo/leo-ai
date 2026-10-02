from abc import ABC, abstractmethod

from betito_bot.agents.eventos import OnEvento


class BaseAgent(ABC):
    """Contrato común que debe cumplir todo agente registrado en el orquestador."""

    name: str
    descripcion: str = ""

    @abstractmethod
    def respond(self, user_text: str, on_event: OnEvento | None = None) -> str:
        ...

    def reset(self) -> None:
        """Olvida el historial de conversación del agente."""
