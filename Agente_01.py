#Importar librerías.
from dotenv import load_dotenv
from groq import Groq
import os
from Memoria_Simple import SimpleMemory
from tools_monitoreo import Tools
import json

#Cargar las variables de ambiente.
load_dotenv()
MEMORY_MAX_MESSAGES = 20

api_key = os.environ.get("API_KEY_GROQ")
client = Groq(api_key=api_key)
memory = SimpleMemory(MEMORY_MAX_MESSAGES)

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


print("Agente de IA")

def process_response(client: Groq, memory_messages: list[dict], user_text: str) : 
    #Obtener la memoria.s
    messages = [SYSTEM_PROMPT] + memory_messages
    messages.append({"role": "user", "content":user_text})
    
        #Llamada al modelo del lenguaje (LLM).
    while True:
        resp = client.chat.completions.create(
            model = "openai/gpt-oss-20b",
            messages = messages,
            tools = TOOLS,
            max_tokens = 300
        )
    
        #Obtener la respuesta de la IA.
        msg = resp.choices[0].message

        #Verificar si solo es un mensaje (ya que puede ser un llamado a herrramientas).
        if not getattr(msg, "tool_calls", None):
            return msg.content or ""
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
            print(args)
            #Preguntar a qué función desea llamar.
            if name == "get_ultimas_lecturas":
                tools = Tools()
                result =  tools.get_ultimas_lecturas(cultivo = args["cultivo"])
            else:
                #Intenta llamar a otra herramienta.
                print(f"Se intento llamar a una herramienta: {name}")
                result = {"error": f"Herramienta desconocida: {name}"}
            #Agregar a los mensajes el resultado del llamado de la herramienta.
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii = False),
                }
            )

        assistant_text = msg.content or ""
    
        # Ahora debemos de revisar si solo es un mensaje y solo imprimirlo.
        #En caso de que no, vemos si es llamado de la función.
        #Mandas a llamar a la función con los argumentos que nos dió el modelo.
        #En caso de que ya tengamos un mensaje debemos regresarlo al usuario, pero si aún hay otra función por llamar, entonces que la llame.
        #Al finalizar, ahora si responder con un mensaje al usuario.

        
        
    

while True:

    user_text = input("Tú: ").strip()
    if not user_text:
        continue
    if user_text.lower() in ("exit", "salir"):
        break

    assistant_text = process_response(client, memory.messages(), user_text)
    print(f"Asistente: {assistant_text}")

    #Actualizar la memoria.
    memory.add("user", user_text)
    memory.add("assistant",  assistant_text)
    
