import re
import unicodedata

from groq import Groq

from betito_bot.agents.monitoreo_agent import MonitoreoAgent
from betito_bot.agents.sensores_agent import SensoresAgent

# Palabras clave que indican una pregunta sobre el estado/salud de los sensores.
SENSORES_PATRON = re.compile(
    r"\b(sensor\w*|falla\w*|calibr\w*|offline|obsolet\w*|trabad\w*|deposito\w*|nivel\w*|"
    r"co2|lux|ph|ec|dpv|botrytis|sin reportar|no reporta\w*)\b"
)


def _normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in sin_acentos if unicodedata.category(c) != "Mn")


class Orchestrator:
    """Punto único de entrada; enruta cada mensaje al agente correspondiente.

    Ruteo por palabras clave: preguntas sobre sensores, fallas, depósitos o
    variables como CO2/lux/pH/EC van a `sensores`; el resto a `monitoreo`.
    """

    def __init__(self, client: Groq):
        self.default_agent = MonitoreoAgent(client)
        self.agents = {"sensores": SensoresAgent(client)}

    def route(self, user_text: str):
        if SENSORES_PATRON.search(_normalizar(user_text)):
            return self.agents["sensores"]
        return self.default_agent

    def handle(self, user_text: str) -> str:
        return self.route(user_text).respond(user_text)
