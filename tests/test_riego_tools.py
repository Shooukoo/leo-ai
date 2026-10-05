import pytest

from betito_bot.agents.riego_agent import TOOLS_SCHEMA, RiegoAgent
from betito_bot.tools.riego_tools import RiegoTools
from tests.datos import poblar

# 12 h cubren tres riegos del simulador (uno cada 4 h) sea cual sea la hora de la prueba.
MINUTOS = 720


def _sensor(res):
    (sensor,) = res["sensores"]
    assert sensor["sensor_id"] == "suelo-cama1-7en1"
    return sensor


def test_riego_sano(db):
    poblar(db, minutos=MINUTOS)
    s = _sensor(RiegoTools(db).resumen_riego(horas=12))
    assert 3 <= s["total_ciclos"] <= 4
    assert s["duracion_media_min"] == 10 and s["intervalo_medio_min"] == 240
    assert s["ciclos_con_problema"] == []
    assert s["ciclos_por_diagnostico"]["ok"] >= 2
    assert 10 <= s["subida_media_pct"] <= 14


@pytest.mark.parametrize("falla,diagnostico", [
    ("sobre_riego", "sobre_riego"),
    ("riego_sin_efecto", "sin_efecto"),
    ("suelo_plano", "sin_efecto"),
])
def test_detecta_riegos_con_problema(db, falla, diagnostico):
    poblar(db, minutos=MINUTOS, fallas={falla}, falla_min=MINUTOS + 1)
    s = _sensor(RiegoTools(db).resumen_riego(horas=12))
    assert s["ciclos_por_diagnostico"].get(diagnostico, 0) >= 2
    assert "ok" not in s["ciclos_por_diagnostico"]
    assert all(c["diagnostico"] == diagnostico for c in s["ciclos_con_problema"])


def test_ciclos_riego_detalle(db):
    poblar(db, minutos=MINUTOS)
    s = _sensor(RiegoTools(db).ciclos_riego(horas=12, cultivo="fresa"))
    assert s["total_ciclos"] == len(s["ciclos"])
    completos = [c for c in s["ciclos"] if c["diagnostico"] == "ok"]
    assert completos and all(c["duracion_min"] == 10 and c["fin_utc"] > c["inicio_utc"] for c in completos)


def test_sin_datos_de_riego_no_es_cero_riegos(db):
    poblar(db, minutos=60)
    db["lecturas_sensores"].update_many({}, {"$unset": {"riego_activo": ""}})
    s = _sensor(RiegoTools(db).resumen_riego())
    assert s["estado"] == "sin_datos_de_riego" and "total_ciclos" not in s


def test_filtros_y_horas_invalidas(db):
    poblar(db, minutos=5)
    t = RiegoTools(db)
    assert "error" in t.resumen_riego(parcela="Parcela 9")
    assert "error" in t.ciclos_riego(sensor_id="amb-01-sht31")
    assert "error" in t.resumen_riego(horas=0)
    assert "error" in t.resumen_riego(horas=10000)


def test_agente_registra_las_tools_del_esquema():
    agente = RiegoAgent(client=None, tools=RiegoTools(db=object()))
    assert {s["function"]["name"] for s in TOOLS_SCHEMA} == set(agente.registry)
