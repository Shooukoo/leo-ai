"""Lecturas simuladas en una base `mongomock` para las pruebas de tools."""

import datetime
import random

from betito_bot.sensores.catalogo import con_fecha_instalacion
from betito_bot.sensores.simulador import generar_lecturas
from betito_bot.tools.sensores_tools import _ahora


def poblar(db, minutos=180, fallas=frozenset(), falla_min=180):
    """Inserta `minutos` de lecturas hasta ahora; las fallas aplican a los últimos `falla_min`."""
    db["sensores"].insert_many(con_fecha_instalacion())
    ahora = _ahora().replace(second=0, microsecond=0)
    rng = random.Random(1)
    docs = []
    for i in range(minutos, -1, -1):
        t = ahora - datetime.timedelta(minutes=i)
        docs.extend(generar_lecturas(t, rng, set(fallas) if i < falla_min else set()))
    db["lecturas_sensores"].insert_many(docs)
