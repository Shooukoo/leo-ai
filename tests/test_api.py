from fastapi.testclient import TestClient

from betito_bot.api import AVISO_SIN_CLAVE, create_app
from betito_bot.orchestrator.router import Orchestrator
from tests.fakes import FakeClient, resp, tool_call


def _orquestador(*respuestas):
    """Orquestador real con un chat model falso y tools que no tocan Mongo."""
    orq = Orchestrator(FakeClient(respuestas))
    orq.agents["sensores"].registry["estado_sensores"] = lambda **_: {"total_sensores": 8, "con_problemas": []}
    orq.default_agent.registry["get_ultimas_lecturas"] = lambda **_: {"lecturas": []}
    return orq


def _cliente(*respuestas):
    return TestClient(create_app(_orquestador(*respuestas)))


def test_health():
    with _cliente() as c:
        assert c.get("/health").json() == {"status": "ok", "avisos": [AVISO_SIN_CLAVE]}


def test_chat_rutea_y_reporta_herramientas():
    with _cliente(resp(tool_calls=[tool_call("estado_sensores", {"obsoleto_min": 10})]), resp("8 sensores, sin problemas")) as c:
        r = c.post("/chat", json={"mensaje": "¿Cómo están los sensores?"})
    assert r.status_code == 200
    datos = r.json()
    assert len(datos.pop("sesion")) == 32
    assert datos == {
        "agente": "sensores",
        "respuesta": "8 sensores, sin problemas",
        "herramientas": [{"agente": "sensores", "nombre": "estado_sensores", "argumentos": '{"obsoleto_min": 10}', "error": None}],
        "bloqueado": None,
    }


def test_chat_con_agente_explicito():
    with _cliente(resp("a"), resp("b")) as c:
        assert c.post("/chat", json={"mensaje": "hola", "agente": "@sensores"}).json()["agente"] == "sensores"
        assert c.post("/chat", json={"mensaje": "@sensores hola"}).json()["agente"] == "sensores"


def test_chat_con_delegacion():
    with _cliente(
        resp(tool_calls=[tool_call("delegate", {"agent": "sensores", "task": "revisa los sensores"}, id="d1")]),
        resp(tool_calls=[tool_call("estado_sensores", id="e1")]),
        resp("sin problemas"),
        resp("Según sensores, todo bien"),
    ) as c:
        datos = c.post("/chat", json={"mensaje": "¿cómo va el tomate?"}).json()
    assert datos["agente"] == "monitoreo" and datos["respuesta"] == "Según sensores, todo bien"
    assert [(h["agente"], h["nombre"]) for h in datos["herramientas"]] == [("monitoreo", "delegate"), ("sensores", "estado_sensores")]


def test_tool_con_error_se_reporta():
    with _cliente(resp(tool_calls=[tool_call("no_existe")]), resp("no pude")) as c:
        datos = c.post("/chat", json={"mensaje": "hola"}).json()
    assert "desconocida" in datos["herramientas"][0]["error"]


def test_agente_desconocido_da_404():
    with _cliente() as c:
        r = c.post("/chat", json={"mensaje": "hola", "agente": "inexistente"})
    assert r.status_code == 404 and "Disponibles" in r.json()["detail"]


def test_fallo_del_modelo_da_502():
    with _cliente(RuntimeError("Groq no responde")) as c:
        r = c.post("/chat", json={"mensaje": "hola"})
    assert r.status_code == 502 and "Groq no responde" not in r.text and "falló el modelo" in r.json()["detail"]


def test_mensaje_vacio_da_422():
    with _cliente() as c:
        assert c.post("/chat", json={"mensaje": ""}).status_code == 422


def test_agentes_y_reset():
    orq = _orquestador(resp("hola"))
    with TestClient(create_app(orq)) as c:
        assert {a["nombre"] for a in c.get("/agentes").json()} == {"monitoreo", "sensores", "riego", "diagnostico"}
        c.post("/chat", json={"mensaje": "hola", "sesion": "s1"})
        assert orq.default_agent._memorias["s1"].messages()
        assert c.post("/reset").json() == {"ok": True}
    assert not orq.default_agent._memorias


def test_sin_orquestador_responde_503(monkeypatch):
    import betito_bot.api as api

    monkeypatch.setattr(api, "_orquestador_por_defecto", lambda: (None, ["Falta API_KEY_GROQ."]))
    with TestClient(api.create_app()) as c:
        assert c.get("/health").json() == {"status": "degradado", "avisos": ["Falta API_KEY_GROQ.", AVISO_SIN_CLAVE]}
        r = c.post("/chat", json={"mensaje": "hola"})
    assert r.status_code == 503 and "API_KEY_GROQ" in r.json()["detail"]
