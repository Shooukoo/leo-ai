"""Chat model falso de LangChain para probar agentes, consola y API sin Groq."""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


def tool_call(name="suma", args=None, id="c1"):
    return {"name": name, "args": args or {}, "id": id}


def resp(content="", tool_calls=None):
    return AIMessage(content=content, tool_calls=tool_calls or [])


class FakeClient(BaseChatModel):
    """Chat model de LangChain que devuelve respuestas predefinidas y guarda lo que recibe."""

    respuestas: list[Any] = []  # AIMessage, o una excepción para simular un fallo del modelo
    ultima: AIMessage | None = None
    llamadas: list = []
    kwargs: list = []

    def __init__(self, respuestas, **kw):
        super().__init__(respuestas=list(respuestas), **kw)

    @property
    def _llm_type(self) -> str:
        return "falso"

    def bind_tools(self, tools, **kwargs: Any):
        return self.bind(tools=tools, **kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.llamadas.append(list(messages))
        self.kwargs.append(kwargs)
        msg = self.respuestas.pop(0) if self.respuestas else self.ultima
        if isinstance(msg, Exception):
            raise msg
        return ChatResult(generations=[ChatGeneration(message=msg)])
