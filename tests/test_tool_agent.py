import json
from types import SimpleNamespace
from langchain_core.messages import AIMessage

from betito_bot.agents.tool_agent import FALLBACK_TEXT, ToolAgent
from betito_bot.orchestrator.router import Orchestrator
from tests.fakes import FakeClient, resp as _resp, tool_call as _tool_call


def _agente(client, registry, **kw):
    return ToolAgent(client, "sys", [], registry, model="m", **kw)


def test_ejecuta_tool_y_responde():
    client = FakeClient([_resp(tool_calls=[_tool_call(args={"a": 1, "b": 2})]), _resp("el resultado es 3")])
    ag = _agente(client, {"suma": lambda a, b: {"r": a + b}})
    assert ag.respond("suma") == "el resultado es 3"
    tool_msg = client.llamadas[1][-1]
    assert tool_msg.type == "tool" and tool_msg.tool_call_id == "c1" and json.loads(tool_msg.content) == {"r": 3}


def test_error_de_tool_vuelve_al_modelo():
    def rota(**_):
        raise ValueError("boom")

    client = FakeClient([_resp(tool_calls=[_tool_call()]), _resp("ok")])
    ag = _agente(client, {"suma": rota})
    assert ag.respond("x") == "ok"
    assert "boom" in client.llamadas[1][-1].content


def test_tool_desconocida():
    client = FakeClient([_resp(tool_calls=[_tool_call(name="nope")]), _resp("ok")])
    _agente(client, {}).respond("x")
    assert "desconocida" in client.llamadas[1][-1].content


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
    for texto in ["¿Cómo estuvo el riego hoy?", "¿cuándo se regó la fresa?", "hay sobre-riego según el sensor de suelo?", "cada cuánto riegan"]:
        assert o.route(texto).name == "riego", texto
    for texto in ["¿Cómo está el tomate?", "Dame las últimas lecturas de la fresa", "riesgo de heladas"]:
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
    assert [m.content for m in client.llamadas[1]] == ["sys", "segunda"]


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
        Orchestrator(client=None).resolver("@clima hola")


def test_monitoreo_pasa_minutos_a_la_tool():
    from betito_bot.agents.monitoreo_agent import MonitoreoAgent

    llamadas = []
    tools = SimpleNamespace(get_ultimas_lecturas=lambda cultivo, minutos=120: llamadas.append((cultivo, minutos)) or {})
    client = FakeClient([_resp(tool_calls=[_tool_call("get_ultimas_lecturas", {"cultivo": "Fresa", "minutos": 30})]), _resp("ok")])
    assert MonitoreoAgent(client, tools=tools).respond("fresa última media hora") == "ok"
    assert llamadas == [("Fresa", 30)]


def test_enlaza_tools_modelo_y_max_tokens():
    client = FakeClient([_resp("ok")])
    schema = [{"type": "function", "function": {"name": "suma", "description": "Suma", "parameters": {"type": "object", "properties": {}}}}]
    ag = ToolAgent(client, "sys", schema, {}, model="m1")
    ag.model = "m2"  # /model lo cambia en caliente
    ag.respond("x")
    kw = client.kwargs[0]
    assert kw["model"] == "m2" and kw["max_tokens"] == ag.max_tokens
    assert kw["tools"][0]["function"]["name"] == "suma"


def test_tool_call_con_json_invalido_vuelve_al_modelo():
    from langchain_core.messages import InvalidToolCall

    malo = AIMessage(content="", invalid_tool_calls=[InvalidToolCall(name="suma", args="{a:", id="c9", error="JSON inválido")])
    client = FakeClient([malo, _resp("ok")])
    eventos = []
    assert _agente(client, {"suma": lambda: {}}).respond("x", on_event=eventos.append) == "ok"
    assert client.llamadas[1][-1].tool_call_id == "c9"
    assert "JSON inválido" in eventos[2].datos["error"]

