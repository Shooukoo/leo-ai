"""Reglas de validación de lecturas y cálculos agronómicos.

Todo se hace en código (no en el LLM). Los rangos salen de la sección 4 del
documento `docs/sensores.md`.
"""
import datetime
import math
import os

# (mínimo, máximo) válidos, ambos incluidos. Fuera de rango -> aviso.
# pH, NPK, nivel y lux tienen reglas propias más abajo (mensajes específicos).
RANGOS = {
    "temperatura_c": (0, 60),
    "humedad_aire_pct": (0, 100),
    "humedad_suelo_pct": (0, 100),
    "temp_suelo_c": (-40, 80),
    "ec_suelo_us_cm": (0, 9999),
}
CAMPOS_TEMP_AGUA = ("temp_agua_deposito_c", "temp_agua_retorno_c")
RANGO_TEMP_AGUA = (-55, 125)
ERRORES_DS18B20 = {85.0, -127.0}
CO2_MIN, CO2_MAX = 300, 2000
LUX_SATURADO = 65535
DIA_INICIO_H, DIA_FIN_H = 8, 17  # horas locales en las que lux=0 es sospechoso

# Campos numéricos que cada sensor puede publicar (para ignorar el resto del documento).
CAMPOS_MEDICION = (
    "temperatura_c", "humedad_aire_pct", "co2_ppm", "lux", "humedad_suelo_pct",
    "temp_suelo_c", "ec_suelo_us_cm", "ph_suelo", "n_mg_kg", "p_mg_kg", "k_mg_kg",
    "temp_agua_deposito_c", "temp_agua_retorno_c", "nivel_deposito_cm",
    "nivel_deposito_pct", "ec_solucion_ms_cm", "ph_solucion",
)


def hora_local(fecha: datetime.datetime | None) -> int | None:
    if fecha is None:
        return None
    offset = float(os.getenv("TZ_OFFSET_HORAS", "-6"))
    return (fecha + datetime.timedelta(hours=offset)).hour


def validar(doc: dict) -> list[str]:
    """Devuelve la lista de avisos de una lectura (vacía si todo está bien)."""
    avisos: list[str] = []

    for campo, (lo, hi) in RANGOS.items():
        v = doc.get(campo)
        if v is not None and not (lo <= v <= hi):
            avisos.append(f"{campo}={v} fuera de rango ({lo}-{hi})")

    co2 = doc.get("co2_ppm")
    if co2 is not None:
        if co2 > CO2_MAX:
            avisos.append(f"co2_ppm={co2} fuera de la especificación de precisión (>{CO2_MAX})")
        elif co2 < CO2_MIN:
            avisos.append(f"co2_ppm={co2} sospechoso/descalibrado (<{CO2_MIN})")

    lux = doc.get("lux")
    if lux is not None:
        if lux >= LUX_SATURADO:
            avisos.append(f"lux={lux}: sensor saturado, no es un valor real")
        elif lux == 0:
            h = hora_local(doc.get("fecha_hora"))
            if h is not None and DIA_INICIO_H <= h <= DIA_FIN_H:
                avisos.append("lux=0 de día: sensor tapado o con falla")

    if doc.get("ec_suelo_us_cm") is not None and doc["ec_suelo_us_cm"] >= 10000:
        avisos.append("ec_suelo_us_cm saturada (>=10000)")
    ph = doc.get("ph_suelo")
    if ph is not None and not (3 < ph < 9):
        avisos.append(f"ph_suelo={ph} saturado/no confiable (fuera de 3–9)")
    for campo in ("n_mg_kg", "p_mg_kg", "k_mg_kg"):
        if doc.get(campo) is not None and doc[campo] >= 1999:
            avisos.append(f"{campo} saturado (1999); NPK es solo indicativo")

    for campo in CAMPOS_TEMP_AGUA:
        v = doc.get(campo)
        if v is None:
            continue
        if v in ERRORES_DS18B20:
            avisos.append(f"{campo}={v}: valor de error del DS18B20 (arranque o desconectado)")
        elif not (RANGO_TEMP_AGUA[0] <= v <= RANGO_TEMP_AGUA[1]):
            avisos.append(f"{campo}={v} fuera de rango {RANGO_TEMP_AGUA}")

    cm, pct = doc.get("nivel_deposito_cm"), doc.get("nivel_deposito_pct")
    if (cm is not None and cm <= 0) or (pct is not None and pct <= 0):
        avisos.append(f"nivel de depósito en 0 (cm={cm}, pct={pct}): depósito vacío o sensor sin lectura")
    elif cm is not None and not (3 <= cm <= 450):
        avisos.append(f"nivel_deposito_cm={cm} fuera del rango del A02YYUW (3-450)")
    elif pct is not None and pct > 100:
        avisos.append(f"nivel_deposito_pct={pct} mayor a 100")

    for falla in doc.get("fallas") or []:
        avisos.append(f"falla reportada por el firmware: {falla}")

    return avisos


def valores_planos(valores: list[float], minimo_lecturas: int = 30) -> bool:
    """True si hay suficientes lecturas y todas son idénticas (sensor trabado)."""
    return len(valores) >= minimo_lecturas and len(set(valores)) == 1


def discrepancia_sht31(
    lecturas: list[dict], umbral_temp_c: float = 3.0, umbral_hr_pct: float = 10.0
) -> list[str]:
    """Compara los SHT31 de una misma zona; cada dict trae sensor_id, temperatura_c, humedad_aire_pct."""
    avisos = []
    for i, a in enumerate(lecturas):
        for b in lecturas[i + 1:]:
            for campo, umbral in (("temperatura_c", umbral_temp_c), ("humedad_aire_pct", umbral_hr_pct)):
                va, vb = a.get(campo), b.get(campo)
                if va is not None and vb is not None and abs(va - vb) > umbral:
                    avisos.append(
                        f"{a['sensor_id']} y {b['sensor_id']} difieren en {campo}: "
                        f"{va} vs {vb} (umbral {umbral}); posible falla de uno"
                    )
    return avisos


def dpv_kpa(temp_c: float, hr_pct: float) -> float:
    """Déficit de presión de vapor (kPa) con la ecuación de Tetens."""
    svp = 0.6108 * math.exp(17.27 * temp_c / (temp_c + 237.3))
    return round(svp * (1 - hr_pct / 100), 2)


def riesgo_botrytis(temp_c: float, hr_pct: float) -> str:
    """Heurística simple (alto/medio/bajo); no sustituye el criterio agronómico."""
    if hr_pct >= 90 and 15 <= temp_c <= 25:
        return "alto"
    if hr_pct >= 85 and 10 <= temp_c <= 28:
        return "medio"
    return "bajo"
