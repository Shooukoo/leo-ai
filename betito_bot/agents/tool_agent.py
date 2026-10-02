import json
import os
from typing import Callable

from groq import Groq

from betito_bot.agents.base import BaseAgent
from betito_bot.memory.simple_memory import SimpleMemory

DEFAULT_MODEL = "openai/gpt-oss-20b"
MEMORY_MAX_MESSAGES = 20
MAX_ITERATIONS = 5

FALLBACK_TEXT = (
    "No pude completar la consulta: el modelo siguió pidiendo herramientas "
    "sin llegar a una respuesta. Intenta reformular la pregunta."
)


class ToolAgent(BaseAgent):
    """Agente con bucle de tool-calling reutilizable (Groq / formato OpenAI).

    Las subclases definen `name`, el prompt de sistema, el esquema de tools y
    un registro `{nombre_tool: callable}`. El bucle tiene tope de iteraciones
    y cualquier excepción de una tool vuelve al modelo como `{"error": ...}`.
    """

    name = "tool_agent"
    max_tokens = 1500

    def __init__(
        self,
        client: Groq,
        system_prompt: str,
        tools_schema: list[dict],
        registry: dict[str, Callable[..., dict]],
        model: str | None = None,
        max_iterations: int = MAX_ITERATIONS,
    ):
        self.client = client
        self.system_prompt = {"role": "system", "content": system_prompt}
        self.tools_schema = tools_schema
        self.registry = registry
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)
        self.max_iterations = max_iterations
        self.memory = SimpleMemory(MEMORY_MAX_MESSAGES)

    def run_tool(self, name: str, raw_arguments: str | None) -> dict:
        func = self.registry.get(name)
        if func is None:
            return {"error": f"Herramienta desconocida: {name}"}
        try:
            args = json.loads(raw_arguments or "{}")
            return func(**args)
        except Exception as e:  # el modelo debe ver el fallo, no el programa caerse
            return {"error": f"{type(e).__name__}: {e}"}

    def respond(self, user_text: str) -> str:
        messages = [self.system_prompt] + self.memory.messages()
        messages.append({"role": "user", "content": user_text})

        for _ in range(self.max_iterations):
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools_schema,
                max_tokens=self.max_tokens,
            )
            msg = resp.choices[0].message

            if not getattr(msg, "tool_calls", None):
                assistant_text = msg.content or ""
                self.memory.add("user", user_text)
                self.memory.add("assistant", assistant_text)
                return assistant_text

            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                result = self.run_tool(tc.function.name, tc.function.arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

        return FALLBACK_TEXT
