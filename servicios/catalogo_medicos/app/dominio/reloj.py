"""Fecha y hora actuales en la zona de la clínica (ZONA_HORARIA).

El contenedor corre en UTC: sin esto, después de las 21 h en Montevideo
"hoy" ya sería mañana.
"""

import datetime
from zoneinfo import ZoneInfo

from app.config import configuracion


def ahora() -> datetime.datetime:
    """Hora local sin zona, comparable con las fechas y horas de DISPONIBILIDAD."""
    return datetime.datetime.now(ZoneInfo(configuracion.zona_horaria)).replace(tzinfo=None)
