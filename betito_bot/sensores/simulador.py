"""Simulador de lecturas sintéticas con fallas inyectables.

Uso:
    python -m betito_bot.sensores.simulador --limpiar --backfill 24
    python -m betito_bot.sensores.simulador --backfill 24 --falla ph_14 --falla sensor_mudo
    python -m betito_bot.sensores.simulador --backfill 24 --falla sobre_riego --falla-min 480
    python -m betito_bot.sensores.simulador --continuo

Escribe en la BD de `MONGO_URI`/`MONGO_DB_NAME`, colecciones
`MONGO_COLLECTION_SENSORES_LECTURAS` y `MONGO_COLLECTION_SENSORES_CATALOGO`.
"""
import argparse
import datetime
import math
import os
import random
import time

from dotenv import load_dotenv
from pymongo import MongoClient

from betito_bot.sensores.catalogo import ALTURA_DEPOSITO_CM, CATALOGO, con_fecha_instalacion

TZ_OFFSET_H = float(os.getenv("TZ_OFFSET_HORAS", "-6"))

# Riego programado: cada 4 h (hora local) se riega 10 min.
RIEGO_CADA_MIN, RIEGO_DURA_MIN = 240, 10
HUMEDAD_SUELO_BASE, HUMEDAD_SUELO_SUBIDA = 50.0, 12.0


def _hora_decimal(t: datetime.datetime) -> float:
    local = t + datetime.timedelta(hours=TZ_OFFSET_H)
    return local.hour + local.minute / 60


def _riego(t: datetime.datetime) -> tuple[bool, float]:
    """(riego activo, humedad de suelo): sube mientras se riega y baja hasta el siguiente riego."""
    local = t + datetime.timedelta(hours=TZ_OFFSET_H)
    fase = (local.hour * 60 + local.minute) % RIEGO_CADA_MIN
    if fase <= RIEGO_DURA_MIN:
        avance = fase / RIEGO_DURA_MIN
    else:
        avance = (RIEGO_CADA_MIN - fase) / (RIEGO_CADA_MIN - RIEGO_DURA_MIN)
    return fase < RIEGO_DURA_MIN, HUMEDAD_SUELO_BASE + HUMEDAD_SUELO_SUBIDA * avance


def _base(t: datetime.datetime, rng: random.Random) -> dict:
    """Valores 'sanos' de todas las variables en el instante t."""
    h = _hora_decimal(t)
    temp = 22 + 6 * math.sin(2 * math.pi * (h - 9) / 24)
    lux = max(0.0, 60000 * math.sin(math.pi * (h - 6) / 12)) if 6 <= h <= 18 else 0.0
    min_dia = h * 60
    pct = 90 - (min_dia / 1440) * 40
    riego_activo, humedad_suelo = _riego(t)
    return {
        "temperatura_c": round(temp + rng.gauss(0, 0.2), 2),
        "humedad_aire_pct": round(min(95, max(40, 95 - 3 * (temp - 15))) + rng.gauss(0, 0.8), 1),
        "co2_ppm": round((450 if 7 <= h <= 18 else 600) + rng.gauss(0, 8)),
        "lux": round(lux + rng.gauss(0, 50)) if lux > 0 else 0,
        "humedad_suelo_pct": round(humedad_suelo + rng.gauss(0, 0.3), 1),
        "riego_activo": riego_activo,
        "temp_suelo_c": round(temp - 3 + rng.gauss(0, 0.1), 1),
        "ec_suelo_us_cm": round(1500 + rng.gauss(0, 15)),
        "ph_suelo": round(6.2 + rng.gauss(0, 0.02), 2),
        "n_mg_kg": round(120 + rng.gauss(0, 2)),
        "p_mg_kg": round(60 + rng.gauss(0, 1)),
        "k_mg_kg": round(180 + rng.gauss(0, 2)),
        "temp_agua_deposito_c": round(20 + rng.gauss(0, 0.1), 2),
        "temp_agua_retorno_c": round(21 + rng.gauss(0, 0.1), 2),
        "nivel_deposito_cm": round(pct * ALTURA_DEPOSITO_CM / 100, 1),
        "nivel_deposito_pct": round(pct, 1),
    }


def _riego_sin_subida(doc: dict) -> dict:
    """Se riega pero la humedad se queda en su valor base (con su ruido)."""
    _, esperada = _riego(doc["fecha_hora"])
    return {"humedad_suelo_pct": round(doc["humedad_suelo_pct"] - esperada + HUMEDAD_SUELO_BASE, 1)}


# Fallas: nombre -> (sensor_id afectado, modificador o None si deja de reportar).
# El modificador es un dict de valores fijos o una función que recibe la lectura sana.
FALLAS = {
    "sensor_mudo": ("amb-03-sht31", None),
    "ds18b20_85": ("dep-a-agua", {"temp_agua_deposito_c": 85.0, "temp_agua_retorno_c": -127.0}),
    "nivel_0": ("dep-a-nivel", {"nivel_deposito_cm": 0.0, "nivel_deposito_pct": 0.0}),
    "ph_14": ("suelo-cama1-7en1", {"ph_suelo": 14.0}),
    "co2_2500": ("amb-01-scd40", {"co2_ppm": 2500}),
    "lux_saturado": ("amb-01-bh1750", {"lux": 65535}),
    "sht31_discrepante": ("amb-02-sht31", {"temperatura_c": 31.0, "humedad_aire_pct": 45.0}),
    "suelo_plano": ("suelo-cama1-7en1", {"humedad_suelo_pct": 52.0}),
    "sobre_riego": ("suelo-cama1-7en1", lambda doc: {"humedad_suelo_pct": round(doc["humedad_suelo_pct"] + 20, 1)}),
    "riego_sin_efecto": ("suelo-cama1-7en1", _riego_sin_subida),
}


def generar_lecturas(
    t: datetime.datetime, rng: random.Random, fallas: set[str] = frozenset()
) -> list[dict]:
    """Una lectura por sensor activo en el instante t, con las fallas indicadas aplicadas."""
    base = _base(t, rng)
    por_sensor = {FALLAS[f][0]: FALLAS[f][1] for f in fallas}
    sensor_mudo = {FALLAS[f][0] for f in fallas if FALLAS[f][1] is None}
    docs = []
    for s in CATALOGO:
        sid = s["sensor_id"]
        if sid in sensor_mudo:
            continue
        doc = {
            "fecha_hora": t,
            "sensor_id": sid,
            "parcela": s["parcela"],
            **{v: base[v] for v in s["variables"]},
        }
        if s["cultivo"]:
            doc["cultivo"] = s["cultivo"]
        if "humedad_suelo_pct" in s["variables"]:
            doc["riego_activo"] = base["riego_activo"]
        for f in fallas:
            fsid, mod = FALLAS[f]
            if fsid == sid and mod:
                doc.update(mod(doc) if callable(mod) else mod)
        if sid == "amb-02-sht31" and "sht31_discrepante" not in fallas:
            doc["temperatura_c"] = round(doc["temperatura_c"] + 0.3, 2)
        docs.append(doc)
    return docs


def _conectar():
    load_dotenv()
    uri = os.getenv("MONGO_URI")
    if not uri:
        raise SystemExit("Falta la variable de entorno MONGO_URI (revisa tu .env).")
    db = MongoClient(uri)[os.getenv("MONGO_DB_NAME", "LEO_AI")]
    lecturas = db[os.getenv("MONGO_COLLECTION_SENSORES_LECTURAS", "lecturas_sensores")]
    catalogo = db[os.getenv("MONGO_COLLECTION_SENSORES_CATALOGO", "sensores")]
    return lecturas, catalogo


def sembrar_catalogo(catalogo) -> None:
    for s in con_fecha_instalacion():
        catalogo.update_one({"sensor_id": s["sensor_id"]}, {"$set": s}, upsert=True)


def main() -> None:
    p = argparse.ArgumentParser(description="Simulador de sensores del invernadero")
    p.add_argument("--backfill", type=float, default=0, help="horas de historial a generar (1 lectura/min)")
    p.add_argument("--continuo", action="store_true", help="seguir insertando 1 lectura/min")
    p.add_argument("--falla", action="append", default=[], choices=sorted(FALLAS), help="falla a inyectar (repetible)")
    p.add_argument("--falla-min", type=int, default=30, help="minutos finales del backfill con la falla activa")
    p.add_argument("--limpiar", action="store_true", help="borra las lecturas existentes antes de generar")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    lecturas, catalogo = _conectar()
    rng = random.Random(args.seed)
    sembrar_catalogo(catalogo)
    if args.limpiar:
        lecturas.delete_many({})

    ahora = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, second=0, microsecond=0)
    fallas = set(args.falla)

    if args.backfill:
        minutos = int(args.backfill * 60)
        lote = []
        for i in range(minutos, -1, -1):
            t = ahora - datetime.timedelta(minutes=i)
            activas = fallas if i < args.falla_min else set()
            lote.extend(generar_lecturas(t, rng, activas))
            if len(lote) >= 5000:
                lecturas.insert_many(lote)
                lote = []
        if lote:
            lecturas.insert_many(lote)
        print(f"Backfill de {minutos} min listo. Fallas activas en los últimos {args.falla_min} min: {sorted(fallas) or 'ninguna'}")

    if args.continuo:
        print("Modo continuo (Ctrl+C para salir)")
        while True:
            t = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, second=0, microsecond=0)
            lecturas.insert_many(generar_lecturas(t, rng, fallas))
            time.sleep(60)


if __name__ == "__main__":
    main()
