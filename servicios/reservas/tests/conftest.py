"""Fixtures comunes: base SQLite en memoria en lugar de PostgreSQL (con el
índice único parcial, que SQLite también soporta), claves JWT temporales,
un reloj que se puede mover y un catálogo falso.
"""

import datetime
from collections.abc import Iterator
from zoneinfo import ZoneInfo

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.clientes.catalogo import (
    CatalogoNoDisponible,
    DatosReserva,
    DisponibilidadInexistente,
    ServicioInexistente,
    obtener_cliente_catalogo,
)
from app.clientes.usuarios import DatosUsuario, UsuariosNoDisponible, obtener_cliente_usuarios
from app.config import configuracion
from app.db.modelos import ESQUEMA, Base
from app.db.sesion import obtener_sesion
from app.dominio import reloj, tokens
from app.main import app

MONTEVIDEO = ZoneInfo("America/Montevideo")
# Lunes 2 de noviembre de 2026, 10:00 en Montevideo.
AHORA = datetime.datetime(2026, 11, 2, 10, 0, tzinfo=MONTEVIDEO)

GOMEZ = "dr.gomez@ejemplo.com"
ALVAREZ = "dra.alvarez@ejemplo.com"
ANA = "ana.perez@ejemplo.com"
BETO = "beto.diaz@ejemplo.com"

# Franja 7: Gómez (clínica médica, especialidad 1), jueves 5/11 de 9:00 a 9:30.
FRANJA = 7
# Servicio 1 es de clínica médica; el 3 es de pediatría (especialidad 2).
SERVICIO = 1
SERVICIO_DE_OTRA_ESPECIALIDAD = 3


class CatalogoFalso:
    """Reemplaza al cliente HTTP de catálogo: franjas y servicios en memoria."""

    def __init__(self):
        self.servicios = {1: 1, 2: 1, 3: 2}  # id_servicio -> id_especialidad
        self.franjas: dict[int, tuple] = {}
        self.especialidad_de = {GOMEZ: 1, ALVAREZ: 1}
        self.caido = False
        self.consultas = 0
        self.agregar_franja(FRANJA, GOMEZ, datetime.date(2026, 11, 5), "09:00", "09:30")

    def agregar_franja(self, id_, email, fecha, inicio, fin) -> int:
        self.franjas[id_] = (
            email,
            fecha,
            datetime.time.fromisoformat(inicio),
            datetime.time.fromisoformat(fin),
        )
        return id_

    def datos_para_reservar(self, id_disponibilidad: int, id_servicio: int) -> DatosReserva:
        self.consultas += 1
        if self.caido:
            raise CatalogoNoDisponible("timeout")
        if id_disponibilidad not in self.franjas:
            raise DisponibilidadInexistente
        if id_servicio not in self.servicios:
            raise ServicioInexistente
        email, fecha, inicio, fin = self.franjas[id_disponibilidad]
        return DatosReserva(
            id_disponibilidad=id_disponibilidad,
            email_profesional=email,
            fecha=fecha,
            horario_inicio=inicio,
            horario_fin=fin,
            id_especialidad=self.especialidad_de[email],
            id_servicio=id_servicio,
            id_especialidad_servicio=self.servicios[id_servicio],
        )


class UsuariosFalso:
    """Reemplaza al cliente HTTP de usuarios: nombres en memoria."""

    def __init__(self):
        self.usuarios = {ANA: DatosUsuario("Ana", "Pérez"), BETO: DatosUsuario("Beto", "Díaz")}
        self.caido = False
        self.consultas: list[list[str]] = []

    def nombres(self, emails: list[str]) -> dict[str, DatosUsuario]:
        self.consultas.append(list(emails))
        if self.caido:
            raise UsuariosNoDisponible("timeout")
        return {email: self.usuarios[email] for email in emails if email in self.usuarios}


class Reloj:
    def __init__(self):
        self.ahora = AHORA


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
    pem_privada, pem_publica = generar_par_claves()
    publica = tmp_path_factory.mktemp("claves") / "jwt_publica.pem"
    publica.write_bytes(pem_publica)
    return pem_privada, str(publica)


@pytest.fixture(autouse=True)
def clave_publica_de_prueba(claves, monkeypatch) -> Iterator[None]:
    monkeypatch.setattr(configuracion, "ruta_clave_publica_jwt", claves[1])
    monkeypatch.setattr(configuracion, "zona_horaria", "America/Montevideo")
    tokens.olvidar_claves()
    yield
    tokens.olvidar_claves()


@pytest.fixture
def emitir(claves):
    """Firma un token como lo haría usuarios: emitir(email, tipo) -> encabezados."""

    def _emitir(email: str, tipo: str, *, clave: bytes | None = None) -> dict:
        emitido = datetime.datetime.now(datetime.UTC)
        claims = {
            "sub": email,
            "tipo": tipo,
            "iss": "usuarios",
            "iat": emitido,
            "exp": emitido + datetime.timedelta(minutes=60),
        }
        token = jwt.encode(claims, clave or claves[0], algorithm="RS256")
        return {"Authorization": f"Bearer {token}"}

    return _emitir


@pytest.fixture
def como_ana(emitir) -> dict:
    return emitir(ANA, "PACIENTE")


@pytest.fixture
def como_beto(emitir) -> dict:
    return emitir(BETO, "PACIENTE")


@pytest.fixture
def como_gomez(emitir) -> dict:
    return emitir(GOMEZ, "PROFESIONAL")


@pytest.fixture
def como_alvarez(emitir) -> dict:
    return emitir(ALVAREZ, "PROFESIONAL")


@pytest.fixture
def motor() -> Iterator[Engine]:
    # SQLite no tiene esquemas: `reservas.turno` pasa a ser `turno`.
    motor = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": {ESQUEMA: None}},
    )
    Base.metadata.create_all(motor)
    yield motor
    motor.dispose()


@pytest.fixture
def fabrica_sesiones(motor) -> sessionmaker[Session]:
    return sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)


@pytest.fixture
def catalogo() -> CatalogoFalso:
    return CatalogoFalso()


@pytest.fixture
def usuarios() -> UsuariosFalso:
    return UsuariosFalso()


@pytest.fixture
def reloj_fijo() -> Reloj:
    return Reloj()


@pytest.fixture
def cliente(fabrica_sesiones, catalogo, usuarios, reloj_fijo) -> Iterator[TestClient]:
    def sesion_de_prueba() -> Iterator[Session]:
        with fabrica_sesiones() as sesion:
            yield sesion

    app.dependency_overrides[obtener_sesion] = sesion_de_prueba
    app.dependency_overrides[obtener_cliente_catalogo] = lambda: catalogo
    app.dependency_overrides[obtener_cliente_usuarios] = lambda: usuarios
    app.dependency_overrides[reloj.ahora] = lambda: reloj_fijo.ahora
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()


def reserva(id_disponibilidad: int = FRANJA, id_servicio: int = SERVICIO) -> dict:
    return {"id_disponibilidad": id_disponibilidad, "id_servicio": id_servicio}
