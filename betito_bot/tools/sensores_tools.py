import datetime
import os

from dotenv import load_dotenv
from pymongo import MongoClient

from betito_bot.sensores import validacion
from betito_bot.sensores.validacion import CAMPOS_MEDICION

load_dotenv()

OBSOLETO_MIN = 10
VENTANA_PLANO_MIN = 120
MAX_HORAS_HISTORIAL = 720  # 30 días
# lux es 0 toda la noche, así que "plano" no indica falla.
SIN_CHEQUEO_PLANO = {"lux"}
VENTANAS = {"hora": "%Y-%m-%dT%H:00", "dia": "%Y-%m-%d"}


def _ahora() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _iso(fecha: datetime.datetime | None) -> str | None:
    return fecha.isoformat() if fecha else None


def _parse_fecha(valor: str | None, defecto: datetime.datetime) -> datetime.datetime:
    if not valor:
        return defecto
    dt = datetime.datetime.fromisoformat(valor)
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt


class SensoresTools:
    """Funciones de lectura fijas para el agente de sensores (sin consultas libres).

    Todo es solo lectura. Las fechas en Mongo son UTC naive.
    """

    def __init__(self, db=None):
        self.MONGO_URI = os.getenv("MONGO_URI")
        self.DB_NAME = os.getenv("MONGO_DB_NAME", "LEO_AI")
        self.LECTURAS = os.getenv("MONGO_COLLECTION_SENSORES_LECTURAS", "lecturas_sensores")
        self.CATALOGO = os.getenv("MONGO_COLLECTION_SENSORES_CATALOGO", "sensores")
        self._client = None
        self._db = db  # inyectable para pruebas

    def get_db(self):
        if self._db is not None:
            return self._db
        if not self.MONGO_URI:
            raise FileNotFoundError("No se encontró la variable de entorno MONGO_URI. Revisa tu archivo .env")
        self._client = MongoClient(self.MONGO_URI, serverSelectionTimeoutMS=5000)
        self._client.admin.command("ping")
        self._db = self._client[self.DB_NAME]
        return self._db

    def close_connection(self):
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None

    # ---- utilidades internas -------------------------------------------------

    def _sensores_activos(self) -> list[dict]:
        return list(self.get_db()[self.CATALOGO].find({"activo": True}, {"_id": 0}))

    def _ultima(self, sensor_id: str) -> dict | None:
        return self.get_db()[self.LECTURAS].find_one({"sensor_id": sensor_id}, sort=[("fecha_hora", -1)])

    @staticmethod
    def _valores(doc: dict) -> dict:
        return {k: doc[k] for k in CAMPOS_MEDICION if doc.get(k) is not None}

    def _resumen_lectura(self, sensor: dict, doc: dict | None, obsoleto_min: int, ahora) -> dict:
        if doc is None:
            return {"sensor_id": sensor["sensor_id"], "modelo": sensor.get("modelo"), "estado": "sin_datos"}
        hace = (ahora - doc["fecha_hora"]).total_seconds() / 60
        obsoleta = hace > obsoleto_min
        return {
            "sensor_id": sensor["sensor_id"],
            "modelo": sensor.get("modelo"),
            "fecha_hora_utc": _iso(doc["fecha_hora"]),
            "hace_min": round(hace, 1),
            "obsoleta": obsoleta,
            "valores": self._valores(doc),
            "avisos": validacion.validar(doc),
        }

    # ---- tools expuestas al agente -------------------------------------------

    def ultimo_estado(self, cultivo: str | None = None, parcela: str | None = None,
                      obsoleto_min: int = OBSOLETO_MIN) -> dict:
        """Última lectura por sensor de un cultivo o parcela (incluye los ambientales compartidos)."""
        if not cultivo and not parcela:
            return {"error": "Indica cultivo o parcela."}
        obsoleto_min = max(1, obsoleto_min)
        sensores = self._sensores_activos()
        if parcela:
            parcelas = {parcela.lower()}
        else:
            parcelas = {s["parcela"].lower() for s in sensores
                        if (s.get("cultivo") or "").lower() == cultivo.lower()}
        seleccion = [s for s in sensores if s["parcela"].lower() in parcelas]
        if not seleccion:
            return {"cultivo": cultivo, "parcela": parcela, "error": "No hay sensores en el catálogo para esa consulta."}

        ahora = _ahora()
        lecturas = [self._resumen_lectura(s, self._ultima(s["sensor_id"]), obsoleto_min, ahora) for s in seleccion]
        return {
            "cultivo": cultivo,
            "parcelas": sorted(parcelas),
            "umbral_obsoleta_min": obsoleto_min,
            "lecturas": lecturas,
        }

    def estado_sensores(self, obsoleto_min: int = OBSOLETO_MIN,
                        ventana_plano_min: int = VENTANA_PLANO_MIN) -> dict:
        """Sensores sin reportar, con valores fuera de rango, lecturas planas o discrepancias."""
        db = self.get_db()
        ahora = _ahora()
        obsoleto_min, ventana_plano_min = max(1, obsoleto_min), max(1, ventana_plano_min)
        problemas: dict[str, list[str]] = {}
        sht31: dict[str, list[dict]] = {}
        sensores = self._sensores_activos()

        for s in sensores:
            sid = s["sensor_id"]
            doc = self._ultima(sid)
            if doc is None:
                problemas.setdefault(sid, []).append("sin datos en la base")
                continue
            hace = (ahora - doc["fecha_hora"]).total_seconds() / 60
            if hace > obsoleto_min:
                problemas.setdefault(sid, []).append(
                    f"sin reportar hace {hace:.0f} min (última lectura {_iso(doc['fecha_hora'])} UTC)")
                continue
            for aviso in validacion.validar(doc):
                problemas.setdefault(sid, []).append(f"{aviso} [lectura {_iso(doc['fecha_hora'])} UTC]")

            desde = ahora - datetime.timedelta(minutes=ventana_plano_min)
            recientes = list(db[self.LECTURAS].find({"sensor_id": sid, "fecha_hora": {"$gte": desde}}))
            for campo in s.get("variables", []):
                if campo in SIN_CHEQUEO_PLANO:
                    continue
                vals = [r[campo] for r in recientes if r.get(campo) is not None]
                if validacion.valores_planos(vals):
                    problemas.setdefault(sid, []).append(
                        f"{campo} plano en {vals[0]} durante {ventana_plano_min} min: sensor posiblemente trabado")

            if s.get("modelo") == "SHT31":
                sht31.setdefault(s.get("zona", s["parcela"]), []).append(
                    {"sensor_id": sid, **{k: doc.get(k) for k in ("temperatura_c", "humedad_aire_pct")}})

        for zona, lecs in sht31.items():
            for aviso in validacion.discrepancia_sht31(lecs):
                for lec in lecs:
                    problemas.setdefault(lec["sensor_id"], []).append(f"zona {zona}: {aviso}")

        ok = [s["sensor_id"] for s in sensores if s["sensor_id"] not in problemas]
        info = {s["sensor_id"]: s for s in sensores}
        return {
            "total_sensores": len(sensores),
            "con_problemas": [
                {"sensor_id": k, "modelo": info[k].get("modelo"), "ubicacion": info[k].get("ubicacion"), "problemas": v}
                for k, v in problemas.items()
            ],
            "sin_problemas": ok,
        }

    def historial(self, variable: str, horas: int = 24, ventana: str = "hora",
                  desde: str | None = None, hasta: str | None = None,
                  sensor_id: str | None = None, parcela: str | None = None) -> dict:
        """Promedio, mínimo y máximo de una variable por hora o por día."""
        if variable not in CAMPOS_MEDICION:
            return {"error": f"Variable no válida: {variable}", "variables_validas": list(CAMPOS_MEDICION)}
        if ventana not in VENTANAS:
            return {"error": "ventana debe ser 'hora' o 'dia'"}
        if not 0 < horas <= MAX_HORAS_HISTORIAL:
            return {"error": f"horas debe estar entre 1 y {MAX_HORAS_HISTORIAL}."}
        fin = _parse_fecha(hasta, _ahora())
        ini = _parse_fecha(desde, fin - datetime.timedelta(hours=horas))
        filtro = {"fecha_hora": {"$gte": ini, "$lte": fin}, variable: {"$ne": None}}
        if sensor_id:
            filtro["sensor_id"] = sensor_id
        if parcela:
            filtro["parcela"] = parcela
        pipeline = [
            {"$match": filtro},
            {"$group": {
                "_id": {"periodo": {"$dateToString": {"format": VENTANAS[ventana], "date": "$fecha_hora"}},
                        "sensor_id": "$sensor_id"},
                "promedio": {"$avg": f"${variable}"},
                "min": {"$min": f"${variable}"},
                "max": {"$max": f"${variable}"},
                "n": {"$sum": 1},
            }},
            {"$sort": {"_id.periodo": 1, "_id.sensor_id": 1}},
        ]
        filas = [
            {"periodo_utc": r["_id"]["periodo"], "sensor_id": r["_id"]["sensor_id"],
             "promedio": round(r["promedio"], 2), "min": r["min"], "max": r["max"], "n": r["n"]}
            for r in self.get_db()[self.LECTURAS].aggregate(pipeline)
        ]
        return {"variable": variable, "ventana": ventana, "desde_utc": _iso(ini), "hasta_utc": _iso(fin), "filas": filas}

    def nivel_depositos(self, ventana_tendencia_min: int = 60) -> dict:
        """Nivel actual (%, cm) por depósito y tendencia de consumo."""
        db = self.get_db()
        ahora = _ahora()
        salida = []
        for s in self._sensores_activos():
            if "nivel_deposito_pct" not in s.get("variables", []):
                continue
            sid = s["sensor_id"]
            ultima = self._ultima(sid)
            if ultima is None:
                salida.append({"sensor_id": sid, "estado": "sin_datos"})
                continue
            desde = ahora - datetime.timedelta(minutes=ventana_tendencia_min)
            serie = list(db[self.LECTURAS].find(
                {"sensor_id": sid, "fecha_hora": {"$gte": desde}, "nivel_deposito_pct": {"$ne": None}}
            ).sort("fecha_hora", 1))
            item = {
                "sensor_id": sid,
                "fecha_hora_utc": _iso(ultima["fecha_hora"]),
                "hace_min": round((ahora - ultima["fecha_hora"]).total_seconds() / 60, 1),
                "nivel_pct": ultima.get("nivel_deposito_pct"),
                "nivel_cm": ultima.get("nivel_deposito_cm"),
                "avisos": validacion.validar(ultima),
            }
            if len(serie) >= 2:
                horas = (serie[-1]["fecha_hora"] - serie[0]["fecha_hora"]).total_seconds() / 3600
                if horas > 0:
                    pend = (serie[-1]["nivel_deposito_pct"] - serie[0]["nivel_deposito_pct"]) / horas
                    item["tendencia_pct_por_hora"] = round(pend, 2)
                    if pend < 0 and item["nivel_pct"]:
                        item["horas_hasta_vacio"] = round(item["nivel_pct"] / -pend, 1)
            salida.append(item)
        return {"depositos": salida}

    @staticmethod
    def calcular_dpv(temp_c: float, hr_pct: float) -> dict:
        return {"temp_c": temp_c, "hr_pct": hr_pct, "dpv_kpa": validacion.dpv_kpa(temp_c, hr_pct)}

    @staticmethod
    def riesgo_botrytis(temp_c: float, hr_pct: float) -> dict:
        return {"temp_c": temp_c, "hr_pct": hr_pct, "riesgo": validacion.riesgo_botrytis(temp_c, hr_pct),
                "nota": "heurística simple basada en temperatura y humedad relativa"}
