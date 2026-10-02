import re
import unicodedata

from groq import Groq

from betito_bot.agents.base import BaseAgent
from betito_bot.agents.eventos import OnEvento
from betito_bot.agents.monitoreo_agent import MonitoreoAgent
from betito_bot.agents.sensores_agent import SensoresAgent

# Palabras clave que indican una pregunta sobre el estado/salud de los sensores.
SENSORES_PATRON = re.compile(
    r"\b(sensor\w*|falla\w*|calibr\w*|offline|obsolet\w*|trabad\w*|deposito\w*|nivel\w*|"
    r"co2|lux|ph|ec|dpv|botrytis|sin reportar|no reporta\w*)\b"
)


# `@nombre resto del mensaje` fuerza el agente sin pasar por el ruteo.
MENCION_PATRON = re.compile(r"^@(\w+)\s*(.*)$", re.DOTALL)


class AgenteDesconocido(ValueError):
    pass


def _normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in sin_acentos if unicodedata.category(c) != "Mn")


class Orchestrator:
    """Punto único de entrada; enruta cada mensaje al agente correspondiente.

    Ruteo por palabras clave: preguntas sobre sensores, fallas, depósitos o
    variables como CO2/lux/pH/EC van a `sensores`; el resto a `monitoreo`.
    Un mensaje que empieza con `@nombre` va directo a ese agente.
    """

    def __init__(self, client: Groq):
        self.default_agent = MonitoreoAgent(client)
        self.agents: dict[str, BaseAgent] = {
            self.default_agent.name: self.default_agent,
            "sensores": SensoresAgent(client),
        }
        self.ultimo_agente: BaseAgent | None = None

    def route(self, user_text: str) -> BaseAgent:
        if SENSORES_PATRON.search(_normalizar(user_text)):
            return self.agents["sensores"]
        return self.default_agent

    def resolver(self, user_text: str) -> tuple[BaseAgent, str]:
        """Devuelve el agente que debe responder y el texto que recibe."""
        mencion = MENCION_PATRON.match(user_text.strip())
        if mencion is None:
            return self.route(user_text), user_text
        nombre, texto = mencion.groups()
        if nombre.lower() not in self.agents:
            raise AgenteDesconocido(nombre)
        return self.agents[nombre.lower()], texto

    def handle(self, user_text: str, on_event: OnEvento | None = None) -> str:
        agente, texto = self.resolver(user_text)
        self.ultimo_agente = agente
        return agente.respond(texto, on_event)

    def reset(self) -> None:
        for agente in self.agents.values():
            agente.reset()
