"""Motor y sesiones de base de datos, a partir de URL_BASE_DATOS.

El motor se crea la primera vez que se pide una sesión, así importar la
aplicación (por ejemplo, en los tests) no exige una base configurada.
"""

from collections.abc import Iterator
from functools import cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import configuracion


@cache
def obtener_motor() -> Engine:
    return create_engine(configuracion.url_base_datos, pool_pre_ping=True)


@cache
def obtener_fabrica_sesiones() -> sessionmaker[Session]:
    return sessionmaker(bind=obtener_motor(), autoflush=False, expire_on_commit=False)


def obtener_sesion() -> Iterator[Session]:
    """Entrega una sesión por pedido y la cierra al terminar (dependencia de FastAPI)."""
    with obtener_fabrica_sesiones()() as sesion:
        yield sesion
