import datetime
import pytest

from betito_bot.sensores import validacion as v
from betito_bot.sensores.validacion import semaforo_cultivo

MEDIODIA_UTC = datetime.datetime(2026, 9, 10, 18, 0)  # 12:00 hora local (UTC-6)
NOCHE_UTC = datetime.datetime(2026, 9, 11, 6, 0)  # 00:00 local


def test_lectura_normal_sin_avisos():
    doc = {"temperatura_c": 24.5, "humedad_aire_pct": 65.0, "co2_ppm": 480, "lux": 30000,
           "ph_suelo": 6.2, "temp_agua_deposito_c": 20.1, "nivel_deposito_cm": 60.0,
           "fecha_hora": MEDIODIA_UTC}
    assert v.validar(doc) == []


def test_ds18b20_valores_de_error():
    assert any("DS18B20" in a for a in v.validar({"temp_agua_deposito_c": 85.0}))
    assert any("DS18B20" in a for a in v.validar({"temp_agua_retorno_c": -127.0}))


def test_nivel_cero():
    assert v.validar({"nivel_deposito_cm": 0.0, "nivel_deposito_pct": 0.0})


def test_ph_fuera_de_rango():
    assert any("ph_suelo" in a for a in v.validar({"ph_suelo": 14.0}))


def test_co2_sobre_especificacion_y_descalibrado():
    assert any("co2_ppm" in a for a in v.validar({"co2_ppm": 2500}))
    assert any("descalibrado" in a for a in v.validar({"co2_ppm": 250}))


def test_lux_saturado():
    assert any("saturado" in a for a in v.validar({"lux": 65535}))


def test_lux_cero_solo_es_falla_de_dia():
    assert v.validar({"lux": 0, "fecha_hora": MEDIODIA_UTC})
    assert v.validar({"lux": 0, "fecha_hora": NOCHE_UTC}) == []


def test_fallas_del_firmware():
    assert any("modbus" in a for a in v.validar({"fallas": ["crc modbus invalido"]}))


def test_valores_planos():
    assert v.valores_planos([52.0] * 40)
    assert not v.valores_planos([52.0] * 5)
    assert not v.valores_planos([52.0] * 39 + [52.1])


def test_discrepancia_sht31():
    a = {"sensor_id": "amb-01-sht31", "temperatura_c": 24.0, "humedad_aire_pct": 60.0}
    b = {"sensor_id": "amb-02-sht31", "temperatura_c": 24.4, "humedad_aire_pct": 61.0}
    c = {"sensor_id": "amb-02-sht31", "temperatura_c": 31.0, "humedad_aire_pct": 45.0}
    assert v.discrepancia_sht31([a, b]) == []
    assert len(v.discrepancia_sht31([a, c])) == 2


def test_dpv_y_botrytis():
    assert v.dpv_kpa(25, 60) == 1.27
    assert v.riesgo_botrytis(20, 92) == "alto"
    assert v.riesgo_botrytis(28, 50) == "bajo"

@pytest.mark.parametrize("dpv,riesgo,esperado", [
    (1.0, "bajo", "verde"), (0.8, "bajo", "verde"), (1.2, "bajo", "verde"),      # bordes del ideal
    (1.0, "medio", "amarillo"),                                                   # gana el riesgo
    (0.6, "bajo", "amarillo"), (1.4, "bajo", "amarillo"),                         # gana el DPV
    (0.4, "bajo", "amarillo"), (1.6, "bajo", "amarillo"),                         # bordes de lo aceptable
    (0.3, "bajo", "rojo"), (1.7, "bajo", "rojo"),
    (1.0, "alto", "rojo"), (0.6, "alto", "rojo"),
    (None, "bajo", "sin_datos"), (1.0, None, "sin_datos"),
])
def test_semaforo_cultivo(dpv, riesgo, esperado):
    assert semaforo_cultivo(dpv, riesgo) == esperado


def test_semaforo_riesgo_invalido():
    with pytest.raises(ValueError):
        semaforo_cultivo(1.0, "extremo")