import json

from groq import Groq

from leo_ai.agents.base import BaseAgent
from leo_ai.memory.simple_memory import SimpleMemory
from leo_ai.tools.monitoreo_tools import MonitoreoTools

MEMORY_MAX_MESSAGES = 20

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_ultimas_lecturas",
            "description": "Revisa la base de datos para traer las lecturas de un cultivo en los últimos 120 minutos,"
                           "o en su defecto, traer la última lectura registrada en la base de dicho cultivo."
                           "Recibe el parámetro cultivo que es el nombre del cultivo que queremos ver su último registro.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cultivo": {
                        "type": "string",
                        "description": 'Es el nombre del cultivo del que queremos saber sus últimos o último registro.',
                    },
                    "minutos": {
                        "type": "string",
                        "description": 'Es la cantidad de tiempo anterior a la petición actual para saber qué registros presentar como últimos.',
                    },
                },
                "required": ["cultivo"],
            },
        },
    },
]

SYSTEM_PROMPT = {
    "role": "system",
    "content": ("Eres un asistente de monitoreo agrícola que ayuda a tomar deciciones sobre recoemndaciones de los cultivos por medio de datos ya existentes.")
}


class MonitoreoAgent(BaseAgent):
    name = "monitoreo"

    def __init__(self, client: Groq):
        self.client = client
        self.memory = SimpleMemory(MEMORY_MAX_MESSAGES)
        self.tools = MonitoreoTools()

    def respond(self, user_text: str) -> str:
        messages = [SYSTEM_PROMPT] + self.memory.messages()
        messages.append({"role": "user", "content": user_text})

        #Llamada al modelo del lenguaje (LLM).
        while True:
            resp = self.client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=messages,
                tools=TOOLS,
                max_tokens=300,
            )

            #Obtener la respuesta de la IA.
            msg = resp.choices[0].message

            #Verificar si solo es un mensaje (ya que puede ser un llamado a herrramientas).
            if not getattr(msg, "tool_calls", None):
                assistant_text = msg.content or ""
                self.memory.add("user", user_text)
                self.memory.add("assistant", assistant_text)
                return assistant_text

            #Existe un llamado a herramientas.
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls":
                        [
                            {
                                #Obtener el id de la función.
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                }
                            }
                            for tc in msg.tool_calls
                        ]
                }
            )

            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments or "{}")
                #Preguntar a qué función desea llamar.
                if name == "get_ultimas_lecturas":
                    result = self.tools.get_ultimas_lecturas(cultivo=args["cultivo"])
                else:
                    #Intenta llamar a otra herramienta.
                    result = {"error": f"Herramienta desconocida: {name}"}
                #Agregar a los mensajes el resultado del llamado de la herramienta.
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
