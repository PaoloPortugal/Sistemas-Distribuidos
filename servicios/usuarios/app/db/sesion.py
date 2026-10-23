"""Motor y sesiones de base de datos, a partir de URL_BASE_DATOS."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import configuracion

motor = create_engine(configuracion.url_base_datos, pool_pre_ping=True)

FabricaSesiones = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)


def obtener_sesion() -> Iterator[Session]:
    """Entrega una sesión por pedido y la cierra al terminar (dependencia de FastAPI)."""
    with FabricaSesiones() as sesion:
        yield sesion
