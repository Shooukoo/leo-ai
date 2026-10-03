import json
from types import SimpleNamespace

from betito_bot.agents.tool_agent import FALLBACK_TEXT, ToolAgent
from betito_bot.orchestrator.router import Orchestrator


def _tool_call(name="suma", args=None, id="c1"):
    return SimpleNamespace(id=id, function=SimpleNamespace(name=name, arguments=json.dumps(args or {})))


def _resp(content=None, tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))])


class FakeClient:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.llamadas.append(kw["messages"][:])
        return self.respuestas.pop(0) if self.respuestas else self.ultima

    ultima = None


def _agente(client, registry, **kw):
    return ToolAgent(client, "sys", [], registry, model="m", **kw)


def test_ejecuta_tool_y_responde():
    client = FakeClient([_resp(tool_calls=[_tool_call(args={"a": 1, "b": 2})]), _resp("el resultado es 3")])
    ag = _agente(client, {"suma": lambda a, b: {"r": a + b}})
    assert ag.respond("suma") == "el resultado es 3"
    tool_msg = client.llamadas[1][-1]
    assert tool_msg["role"] == "tool" and json.loads(tool_msg["content"]) == {"r": 3}


def test_error_de_tool_vuelve_al_modelo():
    def rota(**_):
        raise ValueError("boom")

    client = FakeClient([_resp(tool_calls=[_tool_call()]), _resp("ok")])
    ag = _agente(client, {"suma": rota})
    assert ag.respond("x") == "ok"
    assert "boom" in client.llamadas[1][-1]["content"]


def test_tool_desconocida():
    client = FakeClient([_resp(tool_calls=[_tool_call(name="nope")]), _resp("ok")])
    _agente(client, {}).respond("x")
    assert "desconocida" in client.llamadas[1][-1]["content"]


def test_tope_de_iteraciones():
    client = FakeClient([])
    client.ultima = _resp(tool_calls=[_tool_call()])
    ag = _agente(client, {"suma": lambda: {}}, max_iterations=3)
    assert ag.respond("x") == FALLBACK_TEXT
    assert len(client.llamadas) == 3


def test_ruteo():
    o = Orchestrator(client=None)
    for texto in ["¿Cómo están los sensores?", "¿Cuál es el nivel del depósito?", "hay alguna falla?", "CO2 actual", "el pH está bien?"]:
        assert o.route(texto).name == "sensores", texto
    for texto in ["¿Cómo está el tomate?", "Dame las últimas lecturas de la fresa"]:
        assert o.route(texto).name == "monitoreo", texto


def test_emite_eventos_en_orden():
    client = FakeClient([_resp(tool_calls=[_tool_call(args={"a": 1, "b": 2})]), _resp("3")])
    ag = _agente(client, {"suma": lambda a, b: {"r": a + b}})
    eventos = []
    ag.respond("suma", on_event=eventos.append)
    assert [e.tipo for e in eventos] == ["pensando", "tool_call", "tool_result", "pensando"]
    assert eventos[1].datos == {"nombre": "suma", "argumentos": '{"a": 1, "b": 2}'}
    assert eventos[2].datos == {"nombre": "suma", "error": None, "resultado": {"r": 3}}


def test_evento_de_tool_con_error():
    client = FakeClient([_resp(tool_calls=[_tool_call(name="nope")]), _resp("ok")])
    eventos = []
    _agente(client, {}).respond("x", on_event=eventos.append)
    assert "desconocida" in eventos[2].datos["error"]


def test_reset_borra_memoria():
    client = FakeClient([_resp("hola"), _resp("otra")])
    ag = _agente(client, {})
    ag.respond("primera")
    ag.reset()
    ag.respond("segunda")
    assert [m["content"] for m in client.llamadas[1]] == ["sys", "segunda"]


def test_mencion_fuerza_agente():
    o = Orchestrator(client=None)
    agente, texto = o.resolver("@sensores ¿y la parcela 2?")
    assert agente.name == "sensores" and texto == "¿y la parcela 2?"
    agente, texto = o.resolver("@Monitoreo ¿cómo están los sensores?")
    assert agente.name == "monitoreo" and texto == "¿cómo están los sensores?"


def test_mencion_desconocida():
    import pytest
    from betito_bot.orchestrator.router import AgenteDesconocido

    with pytest.raises(AgenteDesconocido):
        Orchestrator(client=None).resolver("@riego hola")


def test_monitoreo_pasa_minutos_a_la_tool():
    from betito_bot.agents.monitoreo_agent import MonitoreoAgent

    llamadas = []
    tools = SimpleNamespace(get_ultimas_lecturas=lambda cultivo, minutos=120: llamadas.append((cultivo, minutos)) or {})
    client = FakeClient([_resp(tool_calls=[_tool_call("get_ultimas_lecturas", {"cultivo": "Fresa", "minutos": 30})]), _resp("ok")])
    assert MonitoreoAgent(client, tools=tools).respond("fresa última media hora") == "ok"
    assert llamadas == [("Fresa", 30)]
