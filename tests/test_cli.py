from prompt_toolkit.document import Document

from betito_bot.cli import LeoCompleter, formatear_argumentos


def _completar(texto):
    completer = LeoCompleter({"sensores": "salud", "monitoreo": "lecturas"})
    return [c.text for c in completer.get_completions(Document(texto), None)]


def test_completa_comandos():
    assert _completar("/a") == ["/ayuda", "/agentes"]
    assert _completar("/li") == ["/limpiar"]


def test_completa_agentes():
    assert _completar("@s") == ["@sensores"]
    assert _completar("@") == ["@sensores", "@monitoreo"]


def test_no_completa_texto_normal_ni_despues_del_primer_espacio():
    assert _completar("hola") == []
    assert _completar("@sensores /a") == []


def test_formatear_argumentos():
    assert formatear_argumentos('{"cultivo": "Fresa", "minutos": 30}') == 'cultivo="Fresa", minutos=30'
    assert formatear_argumentos("") == ""
    assert formatear_argumentos("no json") == "no json"


def test_completa_skills():
    completer = LeoCompleter({}, {"reporte-diario": "Reporte del día"})
    assert [c.text for c in completer.get_completions(Document("/rep"), None)] == ["/reporte-diario"]


def test_skill_y_delegacion_desde_la_consola():
    from io import StringIO

    from rich.console import Console

    from betito_bot.cli import Interfaz
    from betito_bot.core.skills import Skill
    from betito_bot.orchestrator.router import Orchestrator
    from tests.fakes import FakeClient, resp, tool_call

    class SkillFalsa(Skill):
        def leer(self):
            return "Instrucciones de prueba"

    client = FakeClient([
        resp(tool_calls=[tool_call("delegate", {"agent": "sensores", "task": "revisa"})]),
        resp("todo bien"),
        resp("Reporte listo"),
    ])
    orq = Orchestrator(client, skills={"reporte": SkillFalsa("reporte", "Reporte", None)})
    salida = StringIO()
    ui = Interfaz(orq, console=Console(file=salida, width=120))
    assert ui.ejecutar_comando("/reporte hoy")
    texto = salida.getvalue()
    assert "delega en @sensores" in texto and "● monitoreo" in texto and "Reporte listo" in texto
    assert "Aplica la skill «reporte»" in orq.agents["monitoreo"].memory.messages()[0]["content"]
