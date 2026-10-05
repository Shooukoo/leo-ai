"""Reconstrucción de ciclos de riego y su efecto en la humedad de suelo.

Todo se hace en código (no en el LLM), igual que `validacion.py`. Las funciones
reciben lecturas ordenadas por `fecha_hora` que traen `riego_activo` y
`humedad_suelo_pct` en el mismo documento.
"""
import datetime

from betito_bot.sensores.validacion import RANGOS

HUECO_MAX_MIN = 5          # sin lecturas por más tiempo, no se sabe cuándo terminó el riego
VENTANA_ANTES_MIN = 5      # minutos previos al inicio que definen la humedad de partida
VENTANA_DESPUES_MIN = 30   # minutos tras el fin en los que se busca el pico de humedad
SUBIDA_MIN_PCT = 2.0       # por debajo, el riego no movió la humedad
HUMEDAD_MAX_PCT = 75.0     # pico por encima: sobre-riego (mismo máximo que usa monitoreo)
HUMEDAD_YA_HUMEDO_PCT = 70.0  # regar con el suelo así de húmedo también es sobre-riego

PROBLEMAS = ("sobre_riego", "sin_efecto")


def _minutos(a: datetime.datetime, b: datetime.datetime) -> float:
    return (b - a).total_seconds() / 60


def reconstruir_ciclos(lecturas: list[dict], hueco_max_min: float = HUECO_MAX_MIN) -> list[dict]:
    """Agrupa las rachas de `riego_activo=True` en ciclos con inicio, fin y duración.

    `en_curso`: la serie termina regando. `incompleto`: el ciclo ya estaba activo en la
    primera lectura o hay un hueco de datos dentro, así que su duración no es confiable.
    """
    ciclos: list[dict] = []
    actual: dict | None = None
    previa: datetime.datetime | None = None

    def cerrar(fin: datetime.datetime, **marcas) -> None:
        ciclos.append({**actual, "fin": fin, "duracion_min": round(_minutos(actual["inicio"], fin), 1), **marcas})

    for lectura in lecturas:
        activo = lectura.get("riego_activo")
        if activo is None:
            continue
        t = lectura["fecha_hora"]
        if actual is not None and _minutos(previa, t) > hueco_max_min:
            cerrar(previa, incompleto=True)
            actual = None
        if activo and actual is None:
            actual = {"inicio": t, "en_curso": False, "incompleto": previa is None}
        elif not activo and actual is not None:
            cerrar(t)
            actual = None
        previa = t
    if actual is not None:
        cerrar(previa, en_curso=True)
    return ciclos


def efecto_humedad(ciclo: dict, lecturas: list[dict], siguiente_inicio: datetime.datetime | None = None) -> dict:
    """Humedad antes del riego, pico hasta `VENTANA_DESPUES_MIN` después y cuánto subió."""
    lo, hi = RANGOS["humedad_suelo_pct"]
    serie = [(l["fecha_hora"], l["humedad_suelo_pct"]) for l in lecturas
             if l.get("humedad_suelo_pct") is not None and lo <= l["humedad_suelo_pct"] <= hi]
    inicio = ciclo["inicio"]
    limite = ciclo["fin"] + datetime.timedelta(minutes=VENTANA_DESPUES_MIN)
    if siguiente_inicio is not None:
        limite = min(limite, siguiente_inicio)
    antes = [h for t, h in serie if 0 < _minutos(t, inicio) <= VENTANA_ANTES_MIN]
    despues = [(h, t) for t, h in serie if inicio <= t <= limite and t != siguiente_inicio]
    if not antes or not despues:
        return {"humedad_antes_pct": None, "humedad_pico_pct": None, "subida_pct": None, "min_hasta_pico": None}
    humedad_antes = sum(antes) / len(antes)
    pico, t_pico = max(despues, key=lambda par: par[0])
    return {
        "humedad_antes_pct": round(humedad_antes, 1),
        "humedad_pico_pct": round(pico, 1),
        "subida_pct": round(pico - humedad_antes, 1),
        "min_hasta_pico": round(_minutos(inicio, t_pico), 1),
    }


def diagnosticar(ciclo: dict) -> tuple[str, str]:
    """Devuelve (diagnóstico, motivo): ok, sobre_riego, sin_efecto, en_curso o sin_datos."""
    antes, pico, subida = ciclo.get("humedad_antes_pct"), ciclo.get("humedad_pico_pct"), ciclo.get("subida_pct")
    if antes is None or pico is None:
        return "sin_datos", "no hay lecturas válidas de humedad de suelo alrededor del riego"
    if pico > HUMEDAD_MAX_PCT:
        return "sobre_riego", f"la humedad llegó a {pico} %, por encima del máximo de {HUMEDAD_MAX_PCT:g} %"
    if antes >= HUMEDAD_YA_HUMEDO_PCT:
        return "sobre_riego", f"se regó con el suelo ya húmedo ({antes} %, umbral {HUMEDAD_YA_HUMEDO_PCT:g} %)"
    if ciclo.get("en_curso"):
        return "en_curso", "el riego sigue activo; todavía no se puede medir su efecto"
    if subida < SUBIDA_MIN_PCT:
        return "sin_efecto", (f"la humedad solo cambió {subida} puntos (mínimo esperado {SUBIDA_MIN_PCT:g}): "
                              "revisar bomba, válvula, goteros o el sensor de humedad")
    return "ok", f"la humedad subió {subida} puntos"


def analizar(lecturas: list[dict]) -> list[dict]:
    """Ciclos de riego de la serie, cada uno con su efecto en la humedad y su diagnóstico."""
    ciclos = reconstruir_ciclos(lecturas)
    for i, ciclo in enumerate(ciclos):
        siguiente = ciclos[i + 1]["inicio"] if i + 1 < len(ciclos) else None
        ciclo.update(efecto_humedad(ciclo, lecturas, siguiente))
        ciclo["diagnostico"], ciclo["motivo"] = diagnosticar(ciclo)
    return ciclos


def _media(valores: list[float]) -> float | None:
    return round(sum(valores) / len(valores), 1) if valores else None


def resumir(ciclos: list[dict], horas_cubiertas: float) -> dict:
    """Duración y frecuencia de los ciclos ya analizados y conteo por diagnóstico."""
    duraciones = [c["duracion_min"] for c in ciclos if not c["en_curso"] and not c["incompleto"]]
    inicios = [c["inicio"] for c in ciclos]
    intervalos = [_minutos(a, b) for a, b in zip(inicios, inicios[1:])]
    conteo: dict[str, int] = {}
    for c in ciclos:
        conteo[c["diagnostico"]] = conteo.get(c["diagnostico"], 0) + 1
    return {
        "total_ciclos": len(ciclos),
        "duracion_media_min": _media(duraciones),
        "duracion_min_min": min(duraciones) if duraciones else None,
        "duracion_max_min": max(duraciones) if duraciones else None,
        "intervalo_medio_min": _media(intervalos),
        "riegos_por_dia": round(len(ciclos) * 24 / horas_cubiertas, 1) if horas_cubiertas > 0 else None,
        "minutos_regando": round(sum(c["duracion_min"] for c in ciclos), 1),
        "subida_media_pct": _media([c["subida_pct"] for c in ciclos if c.get("subida_pct") is not None]),
        "ciclos_por_diagnostico": conteo,
    }
