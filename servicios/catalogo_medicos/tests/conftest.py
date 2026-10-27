"""Fixtures comunes: base SQLite en memoria en lugar de PostgreSQL, claves JWT
temporales y un reloj fijo.

SQLite no tiene el EXCLUDE de disponibilidad (se declara solo para
PostgreSQL); un trigger lo imita para poder probar el 409. El comportamiento
real se verifica contra PostgreSQL con Docker.
"""

import datetime
from collections.abc import Iterator

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.clientes.reservas import (
    DisponibilidadConTurno,
    ReservasNoDisponible,
    obtener_cliente_reservas,
)
from app.config import configuracion
from app.db.modelos import ESQUEMA, Base, Especialidad, Profesional, Servicio
from app.db.sesion import obtener_sesion
from app.dominio import reloj, tokens
from app.main import app

# Lunes 2 de noviembre de 2026, 10:00 en la zona de la clínica.
AHORA = datetime.datetime(2026, 11, 2, 10, 0)

TRIGGER_SIN_SUPERPOSICION = """
CREATE TRIGGER sin_superposicion BEFORE INSERT ON disponibilidad
WHEN EXISTS (
    SELECT 1 FROM disponibilidad d
    WHERE d.email_profesional = NEW.email_profesional
      AND d.fecha = NEW.fecha
      AND d.horario_inicio < NEW.horario_fin
      AND d.horario_fin > NEW.horario_inicio
)
BEGIN
    SELECT RAISE(ABORT, 'ex_disponibilidad_sin_superposicion');
END
"""


class ReservasFalso:
    """Reemplaza al cliente HTTP de reservas: turnos reservados y bloqueos en memoria."""

    def __init__(self):
        self.reservadas: set[int] = set()
        self.bloqueadas: set[int] = set()
        self.caido = False
        self.consultas: list[list[int]] = []

    def ocupadas(self, ids: list[int]) -> set[int]:
        self.consultas.append(list(ids))
        if self.caido:
            raise ReservasNoDisponible("timeout")
        return set(ids) & (self.reservadas | self.bloqueadas)

    def bloquear(self, id_disponibilidad: int) -> None:
        if self.caido:
            raise ReservasNoDisponible("timeout")
        if id_disponibilidad in self.reservadas:
            raise DisponibilidadConTurno
        self.bloqueadas.add(id_disponibilidad)

    def desbloquear(self, id_disponibilidad: int) -> None:
        if self.caido:
            raise ReservasNoDisponible("timeout")
        self.bloqueadas.discard(id_disponibilidad)


def generar_par_claves() -> tuple[bytes, bytes]:
    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_privada = privada.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pem_publica = privada.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return pem_privada, pem_publica


@pytest.fixture(scope="session")
def claves(tmp_path_factory) -> tuple[bytes, str]:
    """Clave privada (para firmar tokens como lo haría usuarios) y ruta de la pública."""
    pem_privada, pem_publica = generar_par_claves()
    publica = tmp_path_factory.mktemp("claves") / "jwt_publica.pem"
    publica.write_bytes(pem_publica)
    return pem_privada, str(publica)


@pytest.fixture(autouse=True)
def clave_publica_de_prueba(claves, monkeypatch) -> Iterator[None]:
    monkeypatch.setattr(configuracion, "ruta_clave_publica_jwt", claves[1])
    tokens.olvidar_claves()
    yield
    tokens.olvidar_claves()


@pytest.fixture
def emitir(claves):
    """Firma un token como lo haría usuarios: emitir(email, tipo) -> encabezados."""

    def _emitir(email: str, tipo: str, *, clave: bytes | None = None, **cambios) -> dict:
        emitido = datetime.datetime.now(datetime.UTC)
        claims = {
            "sub": email,
            "tipo": tipo,
            "iss": "usuarios",
            "iat": emitido,
            "exp": emitido + datetime.timedelta(minutes=60),
        } | cambios
        token = jwt.encode(claims, clave or claves[0], algorithm="RS256")
        return {"Authorization": f"Bearer {token}"}

    return _emitir


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
    with motor.begin() as conexion:
        conexion.execute(text(TRIGGER_SIN_SUPERPOSICION))
    yield motor
    motor.dispose()


@pytest.fixture
def fabrica_sesiones(motor) -> sessionmaker[Session]:
    fabrica = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)
    with fabrica() as sesion:
        sesion.add_all(
            [
                Especialidad(id_especialidad=1, nombre="Clínica médica", descripcion="Adultos"),
                Especialidad(id_especialidad=2, nombre="Pediatría"),
                Especialidad(id_especialidad=3, nombre="Dermatología"),
                Servicio(nombre="Consulta general", id_especialidad=1),
                Servicio(nombre="Control preventivo", id_especialidad=1),
                Servicio(nombre="Control del niño sano", id_especialidad=2),
            ]
        )
        sesion.commit()
    return fabrica


@pytest.fixture
def reservas() -> ReservasFalso:
    return ReservasFalso()


@pytest.fixture
def cliente(fabrica_sesiones, reservas) -> Iterator[TestClient]:
    def sesion_de_prueba() -> Iterator[Session]:
        with fabrica_sesiones() as sesion:
            yield sesion

    app.dependency_overrides[obtener_sesion] = sesion_de_prueba
    app.dependency_overrides[obtener_cliente_reservas] = lambda: reservas
    app.dependency_overrides[reloj.ahora] = lambda: AHORA
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()


@pytest.fixture
def profesionales(fabrica_sesiones) -> None:
    """Dos profesionales de clínica médica y una de pediatría."""
    with fabrica_sesiones() as sesion:
        sesion.add_all(
            [
                Profesional(email="dr.gomez@ejemplo.com", matricula="MP-1", id_especialidad=1,
                            nombre="Bruno", apellido="Gómez"),
                Profesional(email="dra.alvarez@ejemplo.com", matricula="MP-2", id_especialidad=1,
                            nombre="Carla", apellido="Álvarez"),
                Profesional(email="dra.suarez@ejemplo.com", matricula="MP-3", id_especialidad=2,
                            nombre="Ana", apellido="Suárez"),
            ]
        )
        sesion.commit()


def datos_profesional(**cambios) -> dict:
    datos = {
        "email": "dr.gomez@ejemplo.com",
        "matricula": "MP-12345",
        "id_especialidad": 1,
        "nombre": "Bruno",
        "apellido": "Gómez",
    }
    return datos | cambios
