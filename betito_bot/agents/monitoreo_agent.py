from groq import Groq

from betito_bot.agents.tool_agent import ToolAgent
from betito_bot.tools.monitoreo_tools import MonitoreoTools

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_ultimas_lecturas",
            "description": "Revisa la base de datos para traer las lecturas de un cultivo en los últimos minutos indicados "
                           "(120 por defecto) o, si no hay ninguna en ese periodo, la última lectura registrada de dicho cultivo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cultivo": {
                        "type": "string",
                        "description": "Nombre del cultivo del que queremos saber sus últimos registros.",
                    },
                    "minutos": {
                        "type": "integer",
                        "description": "Minutos hacia atrás desde ahora para considerar una lectura como reciente (default 120).",
                    },
                },
                "required": ["cultivo"],
            },
        },
    },
]

SYSTEM_PROMPT = (
    "Eres un asistente de monitoreo agrícola que ayuda a tomar decisiones y dar "
    "recomendaciones sobre los cultivos a partir de los datos existentes."
)


class MonitoreoAgent(ToolAgent):
    name = "monitoreo"
    descripcion = "Lecturas recientes por cultivo y recomendaciones generales (agente por defecto)."

    def __init__(self, client: Groq, tools: MonitoreoTools | None = None):
        self.tools = tools or MonitoreoTools()
        super().__init__(
            client,
            system_prompt=SYSTEM_PROMPT,
            tools_schema=TOOLS_SCHEMA,
            registry={"get_ultimas_lecturas": self.tools.get_ultimas_lecturas},
        )
