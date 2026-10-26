"""Fecha y hora actuales, y el instante en que empieza una franja.

Las franjas se guardan como fecha y hora locales de la clínica
(ZONA_HORARIA); para compararlas con "ahora" se les agrega esa zona.
"""

import datetime
from zoneinfo import ZoneInfo

from app.config import configuracion


def zona() -> ZoneInfo:
    return ZoneInfo(configuracion.zona_horaria)


def ahora() -> datetime.datetime:
    """Instante actual con zona horaria (se guarda como timestamptz)."""
    return datetime.datetime.now(zona())


def instante(fecha: datetime.date, hora: datetime.time) -> datetime.datetime:
    """Fecha y hora locales de una franja como instante con zona."""
    return datetime.datetime.combine(fecha, hora, tzinfo=zona())
