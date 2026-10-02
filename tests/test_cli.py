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
