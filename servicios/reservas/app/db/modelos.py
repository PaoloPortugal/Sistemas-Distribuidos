"""Modelos de persistencia del servicio de reservas (esquema `reservas`).

email_paciente, id_disponibilidad e id_servicio apuntan a otros servicios:
no son FK en la base. Se validan contra el token y contra catálogo al
reservar.
"""

import datetime
import uuid

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Identity,
    Index,
    MetaData,
    String,
    Time,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ESQUEMA = "reservas"

# Nombres fijos para las restricciones: Alembic puede manejarlas y los errores
# de PostgreSQL indican qué regla se violó.
CONVENCION_NOMBRES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

RESERVADO = "RESERVADO"
CANCELADO = "CANCELADO"
FINALIZADO = "FINALIZADO"
PACIENTE = "PACIENTE"
PROFESIONAL = "PROFESIONAL"

TURNO_CONFIRMADO = "turno.confirmado"
TURNO_CANCELADO = "turno.cancelado"

SOLO_RESERVADOS = text("estado = 'RESERVADO'")


class Base(DeclarativeBase):
    metadata = MetaData(schema=ESQUEMA, naming_convention=CONVENCION_NOMBRES)


class Turno(Base):
    __tablename__ = "turno"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('RESERVADO', 'CANCELADO', 'FINALIZADO')", name="estado_valido"
        ),
        CheckConstraint(
            "cancelado_por IN ('PACIENTE', 'PROFESIONAL')", name="cancelado_por_valido"
        ),
        # Solo un turno cancelado tiene datos de cancelación (el motivo es opcional).
        CheckConstraint(
            "(estado = 'CANCELADO' AND fecha_cancelacion IS NOT NULL AND cancelado_por IS NOT NULL)"
            " OR (estado <> 'CANCELADO' AND fecha_cancelacion IS NULL"
            " AND motivo_cancelacion IS NULL AND cancelado_por IS NULL)",
            name="cancelacion_coherente",
        ),
        CheckConstraint("fecha_cancelacion >= fecha_creacion", name="cancelacion_posterior"),
        CheckConstraint("email_paciente = lower(email_paciente)", name="email_paciente_minusculas"),
        # Regla clave contra la doble reserva: como máximo un turno RESERVADO por
        # disponibilidad. La decide PostgreSQL, nunca una consulta previa.
        Index(
            "ux_turno_disponibilidad_reservada",
            "id_disponibilidad",
            unique=True,
            postgresql_where=SOLO_RESERVADOS,
            sqlite_where=SOLO_RESERVADOS,
        ),
        Index("ix_turno_email_paciente", "email_paciente"),
        Index("ix_turno_profesional_fecha", "email_profesional", "fecha"),
    )

    id_turno: Mapped[int] = mapped_column(Identity(), primary_key=True)
    email_paciente: Mapped[str] = mapped_column(String(254))
    id_disponibilidad: Mapped[int]
    id_servicio: Mapped[int]
    estado: Mapped[str] = mapped_column(String(20))
    fecha_creacion: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    fecha_cancelacion: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_cancelacion: Mapped[str | None] = mapped_column(String(500))
    cancelado_por: Mapped[str | None] = mapped_column(String(20))

    # Copia de la DISPONIBILIDAD al reservar (ADR 006): permite cancelar y ver
    # la agenda sin consultar a catálogo. El dato de verdad está en catálogo.
    email_profesional: Mapped[str] = mapped_column(String(254))
    fecha: Mapped[datetime.date] = mapped_column(Date)
    horario_inicio: Mapped[datetime.time] = mapped_column(Time)
    horario_fin: Mapped[datetime.time] = mapped_column(Time)


class EventoSaliente(Base):
    """Outbox (ADR 005): eventos escritos en la misma transacción que el turno.

    Un publicador los envía a RabbitMQ y completa `publicado_en` (próxima etapa).
    """

    __tablename__ = "evento_saliente"
    __table_args__ = (
        CheckConstraint(
            "tipo IN ('turno.confirmado', 'turno.cancelado')", name="tipo_valido"
        ),
        Index(
            "ix_evento_saliente_pendiente",
            "creado_en",
            postgresql_where=text("publicado_en IS NULL"),
        ),
    )

    id_evento: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    publicado_en: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))


class DisponibilidadBloqueada(Base):
    """Horarios que catálogo está borrando o ya borró (ADR 003): no se reservan.

    Tabla técnica, fuera del MER. Catálogo bloquea antes de borrar y solo
    desbloquea si no pudo borrar; el bloqueo de un horario borrado queda para
    siempre, así una reserva que consultó a catálogo antes del borrado no
    puede crear un turno sobre un horario que ya no existe.
    """

    __tablename__ = "disponibilidad_bloqueada"

    id_disponibilidad: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    bloqueada_en: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
