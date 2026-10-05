import pytest

from betito_bot.tools.sensores_tools import SensoresTools
from tests.datos import poblar as _poblar


def _problemas(res):
    return {p["sensor_id"]: p["problemas"] for p in res["con_problemas"]}


def test_todo_sano(db):
    _poblar(db)
    res = SensoresTools(db).estado_sensores()
    assert res["total_sensores"] == 8
    assert res["con_problemas"] == []


@pytest.mark.parametrize("falla,sensor,texto", [
    ("sensor_mudo", "amb-03-sht31", "sin reportar"),
    ("ds18b20_85", "dep-a-agua", "DS18B20"),
    ("nivel_0", "dep-a-nivel", "nivel"),
    ("ph_14", "suelo-cama1-7en1", "ph_suelo"),
    ("co2_2500", "amb-01-scd40", "co2_ppm"),
    ("lux_saturado", "amb-01-bh1750", "saturado"),
    ("suelo_plano", "suelo-cama1-7en1", "plano"),
])
def test_cada_falla_se_detecta(db, falla, sensor, texto):
    if falla == "sensor_mudo":
        # el sensor deja de reportar en los últimos 30 min
        _poblar(db, minutos=180, fallas={falla}, falla_min=30)
    else:
        _poblar(db, fallas={falla})
    problemas = _problemas(SensoresTools(db).estado_sensores())
    assert sensor in problemas
    assert any(texto in p for p in problemas[sensor])


def test_discrepancia_sht31(db):
    _poblar(db, fallas={"sht31_discrepante"})
    problemas = _problemas(SensoresTools(db).estado_sensores())
    assert any("difieren" in p for p in problemas["amb-01-sht31"])


def test_ultimo_estado_por_cultivo_incluye_ambientales(db):
    _poblar(db)
    res = SensoresTools(db).ultimo_estado(cultivo="fresa")
    ids = {l["sensor_id"] for l in res["lecturas"]}
    assert {"amb-01-sht31", "amb-01-scd40", "amb-01-bh1750", "suelo-cama1-7en1"} <= ids
    assert "amb-03-sht31" not in ids and "dep-a-nivel" not in ids
    assert all(not l["obsoleta"] for l in res["lecturas"])


def test_ultimo_estado_marca_obsoleta_sin_inventar(db):
    _poblar(db, minutos=60, fallas={"sensor_mudo"}, falla_min=30)
    res = SensoresTools(db).ultimo_estado(cultivo="Jitomate")
    assert res["lecturas"][0]["obsoleta"] is True


def test_ultimo_estado_requiere_filtro_y_cultivo_inexistente(db):
    _poblar(db, minutos=5)
    t = SensoresTools(db)
    assert "error" in t.ultimo_estado()
    assert "error" in t.ultimo_estado(cultivo="Aguacate")


def test_historial_y_variable_invalida(db):
    _poblar(db, minutos=180)
    t = SensoresTools(db)
    res = t.historial("temperatura_c", horas=3, sensor_id="amb-01-sht31")
    assert res["filas"] and all(f["sensor_id"] == "amb-01-sht31" for f in res["filas"])
    assert "error" in t.historial("$where")
    assert "error" in t.historial("temperatura_c", ventana="semana")


def test_nivel_depositos_tendencia(db):
    _poblar(db, minutos=120)
    dep = SensoresTools(db).nivel_depositos()["depositos"][0]
    assert dep["sensor_id"] == "dep-a-nivel"
    assert dep["tendencia_pct_por_hora"] < 0
    assert dep["horas_hasta_vacio"] > 0


def test_calculos():
    t = SensoresTools(db=object())
    assert t.calcular_dpv(25, 60)["dpv_kpa"] == 1.27
    assert t.riesgo_botrytis(20, 92)["riesgo"] == "alto"
