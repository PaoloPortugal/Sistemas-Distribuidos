"""Fixtures comunes: base SQLite en memoria en lugar de PostgreSQL, claves JWT
temporales y un catálogo falso en lugar del servicio catalogo_medicos."""

from collections.abc import Iterator

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.clientes.catalogo import obtener_cliente_catalogo
from app.config import configuracion
from app.db.modelos import ESQUEMA, Base
from app.db.sesion import obtener_sesion
from app.dominio import tokens
from app.main import app

CONTRASENA = "clave-segura-123"


class CatalogoFalso:
    """Reemplaza al cliente HTTP de catálogo y registra las llamadas recibidas."""

    def __init__(self):
        self.creados: list[dict] = []
        self.borrados: list[str] = []
        self.error_al_crear: Exception | None = None
        self.error_al_borrar: Exception | None = None

    def crear_profesional(
        self, *, email: str, matricula: str, id_especialidad: int, nombre: str, apellido: str
    ) -> None:
        self.creados.append(
            {
                "email": email,
                "matricula": matricula,
                "id_especialidad": id_especialidad,
                "nombre": nombre,
                "apellido": apellido,
            }
        )
        if self.error_al_crear is not None:
            raise self.error_al_crear

    def borrar_profesional(self, email: str) -> None:
        self.borrados.append(email)
        if self.error_al_borrar is not None:
            raise self.error_al_borrar


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
def rutas_claves(tmp_path_factory) -> tuple[str, str]:
    directorio = tmp_path_factory.mktemp("claves")
    pem_privada, pem_publica = generar_par_claves()
    privada = directorio / "jwt_privada.pem"
    publica = directorio / "jwt_publica.pem"
    privada.write_bytes(pem_privada)
    publica.write_bytes(pem_publica)
    return str(privada), str(publica)


@pytest.fixture(autouse=True)
def claves_de_prueba(rutas_claves, monkeypatch) -> Iterator[None]:
    privada, publica = rutas_claves
    monkeypatch.setattr(configuracion, "ruta_clave_privada_jwt", privada)
    monkeypatch.setattr(configuracion, "ruta_clave_publica_jwt", publica)
    tokens.olvidar_claves()
    yield
    tokens.olvidar_claves()


@pytest.fixture
def motor() -> Iterator[Engine]:
    # SQLite no tiene esquemas: `usuarios.usuario` pasa a ser `usuario`.
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
    return sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)


@pytest.fixture
def catalogo() -> CatalogoFalso:
    return CatalogoFalso()


@pytest.fixture
def cliente(fabrica_sesiones, catalogo) -> Iterator[TestClient]:
    def sesion_de_prueba() -> Iterator[Session]:
        with fabrica_sesiones() as sesion:
            yield sesion

    app.dependency_overrides[obtener_sesion] = sesion_de_prueba
    app.dependency_overrides[obtener_cliente_catalogo] = lambda: catalogo
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()


def datos_paciente(**cambios) -> dict:
    datos = {
        "email": "ana.perez@ejemplo.com",
        "contrasena": CONTRASENA,
        "nombre": "Ana",
        "apellido": "Pérez",
        "documento": "12345678",
        "telefono": "099123456",
    }
    return datos | cambios


def datos_profesional(**cambios) -> dict:
    datos = {
        "email": "dr.gomez@ejemplo.com",
        "contrasena": CONTRASENA,
        "nombre": "Bruno",
        "apellido": "Gómez",
        "matricula": "MP-12345",
        "id_especialidad": 1,
    }
    return datos | cambios
