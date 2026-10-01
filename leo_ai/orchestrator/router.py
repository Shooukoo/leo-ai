from groq import Groq

from leo_ai.agents.monitoreo_agent import MonitoreoAgent


class Orchestrator:
    """Punto único de entrada; enruta cada mensaje al agente correspondiente.

    Hoy solo existe un agente, así que todo se enruta a él. Al sumar un
    agente nuevo, regístralo aquí y define el criterio de enrutamiento
    (por intención, palabra clave, etc.) en `handle`.
    """

    def __init__(self, client: Groq):
        self.default_agent = MonitoreoAgent(client)

    def handle(self, user_text: str) -> str:
        return self.default_agent.respond(user_text)
