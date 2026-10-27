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
