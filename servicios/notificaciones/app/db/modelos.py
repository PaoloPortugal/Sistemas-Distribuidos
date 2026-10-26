"""Modelos de persistencia del servicio de notificaciones (esquema `notificaciones`).

NOTIFICACION sigue el modelo relacional, con el atributo `destinatario`
(ADR 008). `evento_procesado` y `envio_mail` son tablas técnicas, fuera del
MER, como el outbox de reservas. `id_turno` no es FK: TURNO vive en reservas
y el dato llega en el evento.
"""

import datetime
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ESQUEMA = "notificaciones"

# Nombres fijos para las restricciones: Alembic puede manejarlas y los errores
# de PostgreSQL indican qué regla se violó.
CONVENCION_NOMBRES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

CONFIRMADO = "CONFIRMADO"
CANCELADO = "CANCELADO"
PENDIENTE = "PENDIENTE"
ENVIADO = "ENVIADO"
FALLIDO = "FALLIDO"
PACIENTE = "PACIENTE"
PROFESIONAL = "PROFESIONAL"


class Base(DeclarativeBase):
    metadata = MetaData(schema=ESQUEMA, naming_convention=CONVENCION_NOMBRES)


class Notificacion(Base):
    __tablename__ = "notificacion"
    __table_args__ = (
        CheckConstraint("tipo IN ('CONFIRMADO', 'CANCELADO')", name="tipo_valido"),
        CheckConstraint(
            "estado_notificacion IN ('PENDIENTE', 'ENVIADO', 'FALLIDO')", name="estado_valido"
        ),
        CheckConstraint(
            "destinatario IN ('PACIENTE', 'PROFESIONAL')", name="destinatario_valido"
        ),
        # Un turno se confirma una vez y se cancela como mucho una vez; cada
        # evento avisa a los dos destinatarios. Segunda defensa contra duplicados.
        UniqueConstraint(
            "id_turno", "tipo", "destinatario", name="uq_notificacion_turno_tipo_destinatario"
        ),
    )

    id_notificacion: Mapped[int] = mapped_column(Identity(), primary_key=True)
    id_turno: Mapped[int]
    tipo: Mapped[str] = mapped_column(String(20))
    estado_notificacion: Mapped[str] = mapped_column(String(20))
    destinatario: Mapped[str] = mapped_column(String(20))

    envio: Mapped["EnvioMail"] = relationship(back_populates="notificacion")


class EnvioMail(Base):
    """Datos para mandar el mail de una NOTIFICACION y sus reintentos (ADR 008)."""

    __tablename__ = "envio_mail"
    __table_args__ = (
        CheckConstraint("intentos >= 0", name="intentos_no_negativos"),
        Index("ix_envio_mail_proximo_intento", "proximo_intento"),
    )

    id_notificacion: Mapped[int] = mapped_column(
        ForeignKey(f"{ESQUEMA}.notificacion.id_notificacion", ondelete="CASCADE"),
        primary_key=True,
    )
    email_destinatario: Mapped[str] = mapped_column(String(254))
    asunto: Mapped[str] = mapped_column(String(200))
    cuerpo: Mapped[str] = mapped_column(Text)
    intentos: Mapped[int] = mapped_column(default=0)
    proximo_intento: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    ultimo_error: Mapped[str | None] = mapped_column(Text)
    enviado_en: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))

    notificacion: Mapped[Notificacion] = relationship(back_populates="envio")


class EventoProcesado(Base):
    """event_id ya procesados: el consumidor descarta los repetidos (ADR 008)."""

    __tablename__ = "evento_procesado"

    id_evento: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    recibido_en: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
