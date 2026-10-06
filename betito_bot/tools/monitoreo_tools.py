import os
import re
import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ConfigurationError, OperationFailure

# Cargar variables de entorno desde el archivo .env
load_dotenv()

MAX_MINUTOS = 7 * 24 * 60  # una semana


class MonitoreoTools():
    def __init__(self):
        # La cadena de conexión completa (recomendado, la da Atlas directamente).
        self.MONGO_URI = os.getenv("MONGO_URI")

        # Nombre de la base de datos a usar (separado de la URI para mayor flexibilidad)
        self.DB_NAME = os.getenv("MONGO_DB_NAME", "Mediciones_Sensores")

        self.COLLECTION_NAME = os.getenv("MONGO_COLLECTION_LECTURAS", "Mediciones_Sensores")

        self.UMBRALES = {
            "temperatura_c": {"min": 15, "max": 32},
            "humedad_suelo_pct": {"min": 35, "max": 75},
            "humedad_aire_pct": {"min": 40, "max": 85},
        }

        self._client = None
        self._db = None

    def get_db(self):
        if self._db is not None:
            return self._db

        if not self.MONGO_URI:
            raise FileNotFoundError(
                "No se encontró la variable de entorno MONGO_URI. "
                "Revisa tu archivo .env"
            )

        try:
            self._client = MongoClient(self.MONGO_URI)
            # 'ping' fuerza a probar la conexión de inmediato, en vez de
            # esperar hasta la primera consulta real.
            self._client.admin.command("ping")
        except (ConnectionFailure, ConfigurationError) as e:
            raise ConnectionError(f"No fue posible conectar a MongoDB Atlas: {e}")

        self._db = self._client[self.DB_NAME]
        return self._db

    def check_connection(self):
        """
        Prueba rápida de conectividad, solo confirma que el agente puede hablar con la BD.
        """
        try:
            db = self.get_db()
            collections = db.list_collection_names()
            return {
                "success": True,
                "db_name": self.DB_NAME,
                "collections": collections
            }
        except (ConnectionError, OperationFailure) as e:
            return {
                "success": False,
                "error": str(e)
            }

    def get_ultimas_lecturas(self, cultivo: str, minutos: int = 120):
        """
        Trae las lecturas más recientes (dentro de los últimos `minutos`)
        de todos los sensores asociados a un cultivo dado. Si no hay lecturas
        recientes, hace un segundo intento trayendo la última disponible
        sin importar la fecha, para no dejar al usuario sin respuesta.
        """
        db = self.get_db()
        coleccion = db[self.COLLECTION_NAME]

        minutos = max(1, min(int(minutos), MAX_MINUTOS))
        desde = datetime.datetime.utcnow() - datetime.timedelta(minutes=minutos)

        # re.escape: el nombre viene del modelo y no debe interpretarse como expresión regular.
        filtro_cultivo = {"cultivo": {"$regex": f"^{re.escape(cultivo)}$", "$options": "i"}}

        cursor = coleccion.find(
            {**filtro_cultivo, "fecha_hora": {"$gte": desde}}
        ).sort("fecha_hora", -1)
        lecturas_raw = list(cursor)

        # Fallback: si no hubo lecturas en la ventana de tiempo, traer la última que exista
        if not lecturas_raw:
            ultima = coleccion.find_one(filtro_cultivo, sort=[("fecha_hora", -1)])
            lecturas_raw = [ultima] if ultima else []

        lecturas = []
        for l in lecturas_raw:
            fecha = l.get("fecha_hora")
            lecturas.append({
                "sensor_id": l.get("sensor_id"),
                "parcela": l.get("parcela"),
                "temperatura_c": l.get("temperatura_c"),
                "humedad_aire_pct": l.get("humedad_aire_pct"),
                "humedad_suelo_pct": l.get("humedad_suelo_pct"),
                "riego_activo": l.get("riego_activo"),
                "fecha_hora": fecha.isoformat() if fecha else None
            })

        return {
            "cultivo": cultivo,
            "total_lecturas": len(lecturas),
            "lecturas": lecturas
        }

    def close_connection(self):
        """Cierra el cliente de MongoDB de forma explícita."""
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None


if __name__ == "__main__":
    tools = MonitoreoTools()
    resultado = tools.check_connection()
    print(resultado)
    ultimas = tools.get_ultimas_lecturas("Tomate")
    print(ultimas)
    tools.close_connection()
