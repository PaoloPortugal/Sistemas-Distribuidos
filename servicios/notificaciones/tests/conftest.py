"""Fixtures comunes: base SQLite en memoria en lugar de PostgreSQL, eventos de
ejemplo, un mensaje de RabbitMQ falso y un servidor de correo falso."""

import datetime
import json
import logging
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import configuracion
from app.db.modelos import ESQUEMA, Base
from app.observabilidad import FormateadorJson

configuracion.iniciar_procesos = False

AHORA = datetime.datetime(2026, 11, 2, 13, 0, tzinfo=datetime.UTC)


@pytest.fixture
def motor() -> Iterator[Engine]:
    # SQLite no tiene esquemas: `notificaciones.notificacion` pasa a ser `notificacion`.
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


def evento(tipo="turno.confirmado", **cambios) -> dict:
    datos = {
        "id_evento": str(uuid.uuid4()),
        "tipo": tipo,
        "ocurrido_en": "2026-11-02T10:00:00-03:00",
        "id_turno": 15,
        "id_disponibilidad": 7,
        "id_servicio": 1,
        "email_paciente": "ana.perez@ejemplo.com",
        "email_profesional": "dr.gomez@ejemplo.com",
        "fecha": "2026-11-05",
        "horario_inicio": "09:00:00",
        "horario_fin": "09:30:00",
    }
    if tipo == "turno.cancelado":
        datos |= {"cancelado_por": "PACIENTE", "motivo": "Viaje"}
    return datos | cambios


class MensajeFalso:
    """Imita un mensaje de aio-pika: registra ack, nack y reject en una bitácora."""

    def __init__(
        self,
        cuerpo: bytes | dict,
        bitacora: list[str] | None = None,
        correlation_id: str | None = None,
    ):
        self.body = json.dumps(cuerpo).encode() if isinstance(cuerpo, dict) else cuerpo
        self.message_id = "prueba"
        self.correlation_id = correlation_id
        self.bitacora = bitacora if bitacora is not None else []

    async def ack(self):
        self.bitacora.append("ack")

    async def nack(self, requeue: bool = True):
        self.bitacora.append(f"nack(requeue={requeue})")

    async def reject(self, requeue: bool = False):
        self.bitacora.append(f"reject(requeue={requeue})")


class CorreoFalso:
    """Servidor de correo falso: puede fallar para ciertos destinatarios."""

    def __init__(self):
        self.enviados: list[dict] = []
        self.fallar_para: set[str] = set()

    def enviar(self, *, para: str, asunto: str, cuerpo: str, id_mensaje: str) -> None:
        if para in self.fallar_para:
            raise ConnectionRefusedError("SMTP no disponible")
        self.enviados.append({"para": para, "asunto": asunto, "cuerpo": cuerpo, "id": id_mensaje})


@pytest.fixture
def lineas_json() -> Iterator[list[dict]]:
    """Líneas JSON de los logs, formateadas al emitirse (con el correlation_id de ese momento)."""
    lineas: list[dict] = []

    class Capturador(logging.Handler):
        def emit(self, registro: logging.LogRecord) -> None:
            lineas.append(json.loads(FormateadorJson("notificaciones").format(registro)))

    raiz = logging.getLogger()
    capturador, nivel_anterior = Capturador(), raiz.level
    raiz.addHandler(capturador)
    raiz.setLevel(logging.INFO)
    yield lineas
    raiz.removeHandler(capturador)
    raiz.setLevel(nivel_anterior)
