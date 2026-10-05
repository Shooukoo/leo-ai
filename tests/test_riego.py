import datetime

from betito_bot.sensores import riego

T0 = datetime.datetime(2026, 10, 5, 12, 0)


def _serie(humedades, activos, paso_min=1):
    return [{"fecha_hora": T0 + datetime.timedelta(minutes=i * paso_min), "humedad_suelo_pct": h, "riego_activo": a}
            for i, (h, a) in enumerate(zip(humedades, activos))]


def _un_riego(antes, durante, despues):
    """10 min sin regar en `antes`, 5 min regando hasta `durante` y 20 min en `despues`."""
    humedades = [antes] * 10 + [antes + (durante - antes) * i / 5 for i in range(5)] + [despues] * 20
    return _serie(humedades, [False] * 10 + [True] * 5 + [False] * 20)


def test_reconstruye_inicio_fin_y_duracion():
    ciclos = riego.reconstruir_ciclos(_un_riego(50, 60, 60))
    assert len(ciclos) == 1
    c = ciclos[0]
    assert c["inicio"] == T0 + datetime.timedelta(minutes=10) and c["fin"] == T0 + datetime.timedelta(minutes=15)
    assert c["duracion_min"] == 5 and not c["en_curso"] and not c["incompleto"]


def test_ciclo_en_curso_y_ciclo_cortado_al_inicio():
    lecturas = _serie([50] * 12, [True] * 3 + [False] * 6 + [True] * 3)
    cortado, en_curso = riego.analizar(lecturas)
    assert cortado["incompleto"] and cortado["diagnostico"] == "sin_datos"
    assert en_curso["en_curso"] and en_curso["diagnostico"] == "en_curso"


def test_hueco_de_datos_marca_incompleto():
    lecturas = _serie([50] * 4, [False, True, True, False])
    lecturas[2]["fecha_hora"] += datetime.timedelta(minutes=30)
    lecturas[3]["fecha_hora"] += datetime.timedelta(minutes=30)
    primero, segundo = riego.reconstruir_ciclos(lecturas)
    assert primero["incompleto"] and primero["duracion_min"] == 0
    assert not segundo["incompleto"] and segundo["duracion_min"] == 1


def test_lecturas_sin_riego_activo_se_ignoran():
    lecturas = _serie([50] * 5, [None] * 5)
    assert riego.reconstruir_ciclos(lecturas) == []


def test_riego_normal_mide_la_subida():
    (c,) = riego.analizar(_un_riego(50, 60, 62))
    assert (c["humedad_antes_pct"], c["humedad_pico_pct"], c["subida_pct"]) == (50, 62, 12)
    assert c["min_hasta_pico"] == 5 and c["diagnostico"] == "ok"


def test_riego_sin_efecto():
    (c,) = riego.analizar(_un_riego(50, 50.5, 50.5))
    assert c["diagnostico"] == "sin_efecto" and c["subida_pct"] == 0.5


def test_sobre_riego_por_pico_y_por_suelo_ya_humedo():
    (por_pico,) = riego.analizar(_un_riego(60, 78, 80))
    assert por_pico["diagnostico"] == "sobre_riego" and "80" in por_pico["motivo"]
    (ya_humedo,) = riego.analizar(_un_riego(72, 74, 74))
    assert ya_humedo["diagnostico"] == "sobre_riego" and "ya húmedo" in ya_humedo["motivo"]


def test_humedad_fuera_de_rango_no_cuenta_como_pico():
    lecturas = _un_riego(50, 60, 62)
    lecturas[20]["humedad_suelo_pct"] = 250
    (c,) = riego.analizar(lecturas)
    assert c["humedad_pico_pct"] == 62 and c["diagnostico"] == "ok"


def test_el_pico_no_pasa_del_siguiente_riego():
    humedades = [50] * 6 + [55] * 2 + [56] * 6 + [70] * 2 + [72] * 6
    activos = [False] * 6 + [True] * 2 + [False] * 6 + [True] * 2 + [False] * 6
    primero, segundo = riego.analizar(_serie(humedades, activos))
    assert primero["humedad_pico_pct"] == 56
    assert segundo["humedad_antes_pct"] == 56 and segundo["humedad_pico_pct"] == 72


def test_resumen():
    humedades = ([50] * 10 + [60] * 5 + [62] * 45) * 3
    activos = ([False] * 10 + [True] * 5 + [False] * 45) * 3
    res = riego.resumir(riego.analizar(_serie(humedades, activos)), horas_cubiertas=3)
    assert res["total_ciclos"] == 3 and res["riegos_por_dia"] == 24
    assert res["duracion_media_min"] == 5 and res["intervalo_medio_min"] == 60
    assert res["minutos_regando"] == 15 and res["ciclos_por_diagnostico"] == {"ok": 3}
    assert res["subida_media_pct"] == res["subida_media_ciclos_ok_pct"] == 12


def test_resumen_separa_la_subida_de_los_ciclos_ok():
    humedades = [50] * 10 + [60] * 5 + [62] * 45 + [50] * 10 + [50] * 5 + [50] * 45
    activos = ([False] * 10 + [True] * 5 + [False] * 45) * 2
    res = riego.resumir(riego.analizar(_serie(humedades, activos)), horas_cubiertas=2)
    assert res["ciclos_por_diagnostico"] == {"ok": 1, "sin_efecto": 1}
    assert res["subida_media_pct"] == 6 and res["subida_media_ciclos_ok_pct"] == 12


def test_resumen_sin_ciclos():
    res = riego.resumir([], horas_cubiertas=24)
    assert res["total_ciclos"] == 0 and res["duracion_media_min"] is None and res["riegos_por_dia"] == 0
