import datetime

from betito_bot.sensores import riego
from betito_bot.tools.sensores_tools import SensoresTools, _ahora, _iso

MAX_HORAS = 168   # una semana de lecturas por minuto
MAX_CICLOS = 50


class RiegoTools(SensoresTools):
    """Funciones de lectura fijas para el agente de riego.

    Usa la misma conexión y colecciones que `SensoresTools`. Analiza los sensores
    de suelo cuyas lecturas traen `riego_activo` junto a `humedad_suelo_pct`.
    """

    # ---- utilidades internas -------------------------------------------------

    def _sensores_suelo(self, parcela: str | None, cultivo: str | None, sensor_id: str | None) -> list[dict]:
        sensores = [s for s in self._sensores_activos() if "humedad_suelo_pct" in s.get("variables", [])]
        if sensor_id:
            sensores = [s for s in sensores if s["sensor_id"] == sensor_id]
        if parcela:
            sensores = [s for s in sensores if s["parcela"].lower() == parcela.lower()]
        if cultivo:
            sensores = [s for s in sensores if (s.get("cultivo") or "").lower() == cultivo.lower()]
        return sensores

    @staticmethod
    def _ciclo(c: dict) -> dict:
        item = {
            "inicio_utc": _iso(c["inicio"]),
            "fin_utc": None if c["en_curso"] else _iso(c["fin"]),
            "duracion_min": c["duracion_min"],
            "humedad_antes_pct": c["humedad_antes_pct"],
            "humedad_pico_pct": c["humedad_pico_pct"],
            "subida_pct": c["subida_pct"],
            "min_hasta_pico": c["min_hasta_pico"],
            "diagnostico": c["diagnostico"],
            "motivo": c["motivo"],
        }
        if c["incompleto"]:
            item["nota"] = "ciclo incompleto (cortado por el periodo consultado o por un hueco de datos): duración no confiable"
        return item

    def _analizar(self, horas: float, parcela: str | None, cultivo: str | None, sensor_id: str | None):
        """Devuelve (error, periodo, [(sensor, lecturas, ciclos)])."""
        if not 0 < horas <= MAX_HORAS:
            return {"error": f"horas debe estar entre 1 y {MAX_HORAS}."}, None, []
        sensores = self._sensores_suelo(parcela, cultivo, sensor_id)
        if not sensores:
            return {"error": "No hay sensores de humedad de suelo en el catálogo para esa consulta."}, None, []
        fin = _ahora()
        ini = fin - datetime.timedelta(hours=horas)
        coleccion = self.get_db()[self.LECTURAS]
        resultado = []
        for s in sensores:
            lecturas = list(coleccion.find(
                {"sensor_id": s["sensor_id"], "fecha_hora": {"$gte": ini, "$lte": fin}},
                {"_id": 0, "fecha_hora": 1, "riego_activo": 1, "humedad_suelo_pct": 1},
            ).sort("fecha_hora", 1))
            resultado.append((s, lecturas, riego.analizar(lecturas)))
        return None, {"desde_utc": _iso(ini), "hasta_utc": _iso(fin)}, resultado

    @staticmethod
    def _cabecera(sensor: dict, lecturas: list[dict]) -> dict:
        """Datos del sensor; con `estado` si no hay con qué analizar el riego."""
        item = {k: sensor.get(k) for k in ("sensor_id", "parcela", "cultivo", "ubicacion")}
        if not any(l.get("riego_activo") is not None for l in lecturas):
            item["estado"] = "sin_datos_de_riego"
            item["detalle"] = "No hay lecturas con el estado del riego en el periodo: no se puede saber si se regó."
        return item

    # ---- tools expuestas al agente -------------------------------------------

    def resumen_riego(self, horas: float = 24, parcela: str | None = None, cultivo: str | None = None) -> dict:
        """Duración y frecuencia de los riegos, subida media de humedad y ciclos con problema."""
        error, periodo, analisis = self._analizar(horas, parcela, cultivo, None)
        if error:
            return error
        sensores = []
        for sensor, lecturas, ciclos in analisis:
            item = self._cabecera(sensor, lecturas)
            if "estado" not in item:
                cubiertas = (lecturas[-1]["fecha_hora"] - lecturas[0]["fecha_hora"]).total_seconds() / 3600
                item.update(riego.resumir(ciclos, cubiertas))
                item["ciclos_con_problema"] = [self._ciclo(c) for c in ciclos if c["diagnostico"] in riego.PROBLEMAS][-MAX_CICLOS:]
            sensores.append(item)
        return {**periodo, "umbrales": {
            "subida_minima_pct": riego.SUBIDA_MIN_PCT,
            "humedad_maxima_pct": riego.HUMEDAD_MAX_PCT,
            "suelo_ya_humedo_pct": riego.HUMEDAD_YA_HUMEDO_PCT,
        }, "sensores": sensores}

    def ciclos_riego(self, horas: float = 24, parcela: str | None = None, cultivo: str | None = None,
                     sensor_id: str | None = None) -> dict:
        """Detalle de cada ciclo de riego: inicio, fin, duración, humedad antes, pico y diagnóstico."""
        error, periodo, analisis = self._analizar(horas, parcela, cultivo, sensor_id)
        if error:
            return error
        sensores = []
        for sensor, lecturas, ciclos in analisis:
            item = self._cabecera(sensor, lecturas)
            if "estado" not in item:
                item["total_ciclos"] = len(ciclos)
                item["ciclos"] = [self._ciclo(c) for c in ciclos[-MAX_CICLOS:]]
            sensores.append(item)
        return {**periodo, "sensores": sensores}
