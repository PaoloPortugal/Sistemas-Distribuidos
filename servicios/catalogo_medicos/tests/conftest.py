"""Fixtures comunes: base SQLite en memoria en lugar de PostgreSQL.

SQLite no tiene el EXCLUDE de disponibilidad (se declara solo para
PostgreSQL); la superposición se verifica contra PostgreSQL con Docker.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.modelos import ESQUEMA, Base, Especialidad
from app.db.sesion import obtener_sesion
from app.main import app


@pytest.fixture
def motor() -> Iterator[Engine]:
    # SQLite no tiene esquemas: `catalogo_medicos.profesional` pasa a ser `profesional`.
    motor = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": {ESQUEMA: None}},
    )

    @event.listens_for(motor, "connect")
    def activar_claves_foraneas(conexion_dbapi, _registro):
        conexion_dbapi.execute("PRAGMA foreign_keys = ON")

    Base.metadata.create_all(motor)
    yield motor
    motor.dispose()


@pytest.fixture
def fabrica_sesiones(motor) -> sessionmaker[Session]:
    fabrica = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)
    with fabrica() as sesion:
        sesion.add_all(
            [
                Especialidad(id_especialidad=1, nombre="Clínica médica"),
                Especialidad(id_especialidad=2, nombre="Pediatría"),
            ]
        )
        sesion.commit()
    return fabrica


@pytest.fixture
def cliente(fabrica_sesiones) -> Iterator[TestClient]:
    def sesion_de_prueba() -> Iterator[Session]:
        with fabrica_sesiones() as sesion:
            yield sesion

    app.dependency_overrides[obtener_sesion] = sesion_de_prueba
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()


def datos_profesional(**cambios) -> dict:
    datos = {"email": "dr.gomez@ejemplo.com", "matricula": "MP-12345", "id_especialidad": 1}
    return datos | cambios
