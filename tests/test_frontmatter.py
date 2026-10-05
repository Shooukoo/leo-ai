import pytest

from betito_bot.core import frontmatter
from betito_bot.core.agentes import AgenteMarkdown, cargar_definiciones, leer_definicion
from betito_bot.core.config import Config
from betito_bot.core.sistema import construir_orquestador
from betito_bot.core.skills import cargar_skills, mensaje_para_agente


def test_parsea_escalares_y_listas():
    meta, cuerpo = frontmatter.parsear(
        "---\nname: clima\ndescription: \"Hola: mundo\"\ntools: [a, 'b', c]\n# comentario\nbloque:\n  - x\n  - y\n---\nCuerpo\n"
    )
    assert meta == {"name": "clima", "description": "Hola: mundo", "tools": ["a", "b", "c"], "bloque": ["x", "y"]}
    assert cuerpo == "Cuerpo"


def test_sin_frontmatter_y_lista_vacia():
    assert frontmatter.parsear("solo texto") == ({}, "solo texto")
    assert frontmatter.parsear("---\ntools: []\n---\n")[0] == {"tools": []}


@pytest.mark.parametrize("texto", ["---\nname: x\nsin cierre", "---\n esto no es clave\n---\n"])
def test_frontmatter_invalido(texto):
    with pytest.raises(frontmatter.FrontmatterInvalido):
        frontmatter.parsear(texto)


def _skill(base, nombre, contenido):
    (base / nombre).mkdir(parents=True)
    (base / nombre / "SKILL.md").write_text(contenido, encoding="utf-8")


def test_skills_se_cargan_y_el_cuerpo_se_lee_bajo_demanda(tmp_path):
    _skill(tmp_path, "reporte", "---\nname: reporte\ndescription: Reporte diario\n---\nversión 1")
    _skill(tmp_path, "rota", "---\nname: rota\n---\nsin descripción")
    avisos = []
    skills = cargar_skills(tmp_path, avisos)
    assert list(skills) == ["reporte"]
    assert len(avisos) == 1 and "description" in avisos[0]
    (tmp_path / "reporte" / "SKILL.md").write_text("---\nname: reporte\ndescription: d\n---\nversión 2", encoding="utf-8")
    assert skills["reporte"].leer() == "versión 2"  # no quedó en memoria al cargar


def test_mensaje_de_skill_respeta_la_mencion(tmp_path):
    _skill(tmp_path, "s", "---\nname: s\ndescription: d\n---\nPasos")
    skill = cargar_skills(tmp_path)["s"]
    mensaje = mensaje_para_agente(skill, "@sensores parcela 1")
    assert mensaje.startswith("@sensores Aplica la skill «s»")
    assert "Pasos" in mensaje and mensaje.endswith("parcela 1")


def test_definicion_de_agente(tmp_path):
    ruta = tmp_path / "riego.md"
    ruta.write_text("---\ndescription: Riego\ntools:\n  - historial\nmodel: m1\n---\nPrompt", encoding="utf-8")
    d = leer_definicion(ruta)
    assert (d.name, d.description, d.tools, d.model, d.system_prompt) == ("riego", "Riego", ["historial"], "m1", "Prompt")


@pytest.mark.parametrize("contenido,error", [
    ("---\nname: con-guion\ndescription: d\n---\nP", "nombre"),
    ("---\nname: x\n---\nP", "description"),
    ("---\nname: x\ndescription: d\n---\n", "prompt"),
])
def test_agentes_invalidos_se_omiten(tmp_path, contenido, error):
    (tmp_path / "a.md").write_text(contenido, encoding="utf-8")
    (tmp_path / "README.md").write_text("no es un agente", encoding="utf-8")
    avisos = []
    assert cargar_definiciones(tmp_path, avisos) == []
    assert len(avisos) == 1 and error in avisos[0]


def test_agente_con_tool_desconocida_falla(tmp_path):
    (tmp_path / "x.md").write_text("---\ndescription: d\ntools: [no_existe]\n---\nP", encoding="utf-8")
    with pytest.raises(ValueError, match="no_existe"):
        AgenteMarkdown(leer_definicion(tmp_path / "x.md"), None, {})


def test_construir_orquestador_registra_agentes_y_skills(tmp_path):
    agentes, skills = tmp_path / "agents", tmp_path / "skills"
    agentes.mkdir()
    (agentes / "clima.md").write_text("---\ndescription: Clima\ntools: [calcular_dpv]\n---\nP", encoding="utf-8")
    (agentes / "sensores.md").write_text("---\ndescription: duplicado\n---\nP", encoding="utf-8")
    (agentes / "malo.md").write_text("---\ndescription: d\ntools: [nope]\n---\nP", encoding="utf-8")
    _skill(skills, "rep", "---\nname: rep\ndescription: d\n---\nP")
    orq, avisos = construir_orquestador(Config(skills_dir=skills, agentes_dir=agentes), client=None)
    assert set(orq.agents) == {"monitoreo", "sensores", "riego", "clima"}
    assert orq.agents["clima"].registry["calcular_dpv"](temp_c=25, hr_pct=60)  # la tool real
    assert len(avisos) == 2
    nombres = [s["function"]["name"] for s in orq.default_agent.tools_schema]
    assert nombres == ["get_ultimas_lecturas", "delegate", "usar_skill"]
    assert "clima" in orq.default_agent.tools_schema[1]["function"]["description"]
    assert orq.usar_skill("rep") == {"skill": "rep", "instrucciones": "P"}
