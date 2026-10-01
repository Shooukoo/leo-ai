"""Catálogo de sensores del invernadero (colección `sensores`).

Fuente única para el simulador y para sembrar la BD. Cuando llegue el
hardware real, el catálogo se mantiene en Mongo y este módulo solo siembra.
"""
import datetime

ALTURA_DEPOSITO_CM = 100

_RANGOS = {
    "temperatura_c": [0, 60], "humedad_aire_pct": [0, 100], "co2_ppm": [300, 2000],
    "lux": [1, 65534], "humedad_suelo_pct": [0, 100], "temp_suelo_c": [-40, 80],
    "ec_suelo_us_cm": [0, 9999], "ph_suelo": [3.01, 8.99],
    "n_mg_kg": [0, 1998], "p_mg_kg": [0, 1998], "k_mg_kg": [0, 1998],
    "temp_agua_deposito_c": [-55, 125], "temp_agua_retorno_c": [-55, 125],
    "nivel_deposito_cm": [3, 450],
}


def _sensor(sensor_id, modelo, variables, parcela, cultivo, ubicacion, **extra):
    return {
        "sensor_id": sensor_id,
        "modelo": modelo,
        "variables": variables,
        "parcela": parcela,
        "cultivo": cultivo,
        "ubicacion": ubicacion,
        "rango_valido": {v: _RANGOS[v] for v in variables if v in _RANGOS},
        "activo": True,
        "ultima_calibracion": None,
        **extra,
    }


CATALOGO = [
    _sensor("amb-01-sht31", "SHT31", ["temperatura_c", "humedad_aire_pct"], "Parcela 1", "Fresa", "Zona A, pasillo norte", zona="A"),
    _sensor("amb-02-sht31", "SHT31", ["temperatura_c", "humedad_aire_pct"], "Parcela 1", "Fresa", "Zona A, pasillo sur", zona="A"),
    _sensor("amb-03-sht31", "SHT31", ["temperatura_c", "humedad_aire_pct"], "Parcela 2", "Jitomate", "Zona B", zona="B"),
    _sensor("amb-01-scd40", "SCD40", ["co2_ppm"], "Parcela 1", None, "Zona A, ambiental compartido"),
    _sensor("amb-01-bh1750", "BH1750", ["lux"], "Parcela 1", None, "Zona A, ambiental compartido"),
    _sensor(
        "suelo-cama1-7en1", "Gemho 7 en 1",
        ["humedad_suelo_pct", "temp_suelo_c", "ec_suelo_us_cm", "ph_suelo", "n_mg_kg", "p_mg_kg", "k_mg_kg"],
        "Parcela 1", "Fresa", "Cama 1",
    ),
    _sensor("dep-a-nivel", "A02YYUW", ["nivel_deposito_cm", "nivel_deposito_pct"], "Depósitos", None, "Depósito A",
            geometria={"altura_cm": ALTURA_DEPOSITO_CM}),
    _sensor("dep-a-agua", "DS18B20", ["temp_agua_deposito_c", "temp_agua_retorno_c"], "Depósitos", None, "Depósito A"),
]


def con_fecha_instalacion(ahora: datetime.datetime | None = None) -> list[dict]:
    ahora = ahora or datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return [{**s, "fecha_instalacion": ahora} for s in CATALOGO]
