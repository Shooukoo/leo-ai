from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """Contrato común que debe cumplir todo agente registrado en el orquestador."""

    name: str

    @abstractmethod
    def respond(self, user_text: str) -> str:
        ...
