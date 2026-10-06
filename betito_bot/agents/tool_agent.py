import json
import os
from collections import OrderedDict
from typing import Any, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from betito_bot.agents.base import BaseAgent
from betito_bot.agents.eventos import Evento, OnEvento
from betito_bot.memory.sesion import MAX_SESIONES, SESION
from betito_bot.memory.simple_memory import SimpleMemory
from betito_bot.seguridad.argumentos import validar_argumentos
from betito_bot.seguridad.guardian import revisar_salida
from betito_bot.seguridad.reglas import RECHAZO, REGLAS_COMUNES

DEFAULT_MODEL = "openai/gpt-oss-20b"
MEMORY_MAX_MESSAGES = 20
MAX_ITERATIONS = 5

FALLBACK_TEXT = (
    "No pude completar la consulta: el modelo siguió pidiendo herramientas "
    "sin llegar a una respuesta. Intenta reformular la pregunta."
)

_CLASES_MENSAJE = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}


def a_mensajes(historial: list[dict]) -> list[BaseMessage]:
    """Convierte la memoria (`{"role", "content"}`) a mensajes de LangChain."""
    return [_CLASES_MENSAJE[m["role"]](content=m["content"]) for m in historial]


class ToolAgent(BaseAgent):
    """Agente con bucle de tool-calling reutilizable sobre un chat model de LangChain.

    `client` es un `BaseChatModel` (en producción `ChatGroq`, ver
    `betito_bot/llm/groq_client.py`). Las subclases definen `name`, el prompt
    de sistema, el esquema de tools (formato OpenAI, que `bind_tools` acepta tal
    cual) y un registro `{nombre_tool: callable}`. El bucle tiene tope de
    iteraciones y cualquier excepción de una tool vuelve al modelo como
    `{"error": ...}`. Si se pasa `on_event`, se le avisa cada paso (ver `Evento`).

    Seguridad: al prompt se le añaden `REGLAS_COMUNES`, los argumentos de cada
    tool se validan contra su esquema y la respuesta final pasa por
    `revisar_salida`. La memoria es una por sesión (ver `memory/sesion.py`).
    """

    name = "tool_agent"
    max_tokens = 1500

    def __init__(
        self,
        client: BaseChatModel,
        system_prompt: str,
        tools_schema: list[dict],
        registry: dict[str, Callable[..., dict]],
        model: str | None = None,
        max_iterations: int = MAX_ITERATIONS,
    ):
        self.client = client
        self.system_prompt = SystemMessage(content=f"{system_prompt}\n\n{REGLAS_COMUNES}")
        self.tools_schema = tools_schema
        self.registry = registry
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)
        self.max_iterations = max_iterations
        self._memorias: OrderedDict[str, SimpleMemory] = OrderedDict()

    @property
    def memory(self) -> SimpleMemory:
        """Memoria de la sesión en curso; se crea al primer uso."""
        sesion = SESION.get()
        if sesion not in self._memorias:
            self._memorias[sesion] = SimpleMemory(MEMORY_MAX_MESSAGES)
            if len(self._memorias) > MAX_SESIONES:
                self._memorias.popitem(last=False)
        self._memorias.move_to_end(sesion)
        return self._memorias[sesion]

    def reset(self, todas: bool = False) -> None:
        if todas:
            self._memorias.clear()
        else:
            self._memorias.pop(SESION.get(), None)

    def _schema_de(self, name: str) -> dict | None:
        return next((s for s in self.tools_schema if s["function"]["name"] == name), None)

    def run_tool(self, name: str, args: dict[str, Any]) -> dict:
        func = self.registry.get(name)
        if func is None:
            return {"error": f"Herramienta desconocida: {name}"}
        try:
            schema = self._schema_de(name)
            if schema is not None:
                args = validar_argumentos(schema, args)
            return func(**args)
        except Exception as e:  # el modelo debe ver el fallo, no el programa caerse
            return {"error": f"{type(e).__name__}: {e}"}

    def _emitir(self, on_event: OnEvento | None, tipo: str, **datos) -> None:
        if on_event is not None:
            on_event(Evento(tipo, self.name, datos))

    def _llm(self):
        # Se enlaza en cada respuesta: el orquestador agrega tools (`delegate`) después
        # de construir el agente y `/model` puede cambiar `self.model` en caliente.
        if self.tools_schema:
            return self.client.bind_tools(self.tools_schema, model=self.model, max_tokens=self.max_tokens)
        return self.client.bind(model=self.model, max_tokens=self.max_tokens)

    def respond(self, user_text: str, on_event: OnEvento | None = None) -> str:
        messages = [self.system_prompt, *a_mensajes(self.memory.messages()), HumanMessage(content=user_text)]
        llm = self._llm()

        for _ in range(self.max_iterations):
            self._emitir(on_event, "pensando")
            msg: AIMessage = llm.invoke(messages)
            if not msg.tool_calls and not msg.invalid_tool_calls:
                assistant_text = msg.text or ""
                motivo = revisar_salida(assistant_text, self.system_prompt.content)
                if motivo:  # no se guarda: una respuesta bloqueada no debe quedar como contexto
                    self._emitir(on_event, "bloqueado", etapa="salida", motivo=motivo)
                    return RECHAZO
                self.memory.add("user", user_text)
                self.memory.add("assistant", assistant_text)
                return assistant_text

            messages.append(msg)
            for tc in msg.tool_calls:
                nombre = tc["name"]
                self._emitir(on_event, "tool_call", nombre=nombre, argumentos=json.dumps(tc["args"], ensure_ascii=False))
                result = self.run_tool(nombre, tc["args"])
                error = result.get("error") if isinstance(result, dict) else None
                self._emitir(on_event, "tool_result", nombre=nombre, error=error, resultado=result)
                messages.append(ToolMessage(content=json.dumps(result, ensure_ascii=False, default=str), tool_call_id=tc["id"]))
            for tc in msg.invalid_tool_calls:  # argumentos que no son JSON válido
                nombre = tc.get("name") or "?"
                self._emitir(on_event, "tool_call", nombre=nombre, argumentos=tc.get("args") or "")
                result = {"error": f"Argumentos no válidos: {tc.get('error') or tc.get('args')}"}
                self._emitir(on_event, "tool_result", nombre=nombre, error=result["error"], resultado=result)
                messages.append(ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id=tc.get("id") or ""))

        return FALLBACK_TEXT
