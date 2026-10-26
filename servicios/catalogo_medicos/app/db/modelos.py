"""Modelos de persistencia del servicio de catálogo (esquema `catalogo_medicos`).

PROFESIONAL.email no tiene FK a USUARIO: USUARIO vive en el servicio de
usuarios y la especialización total se garantiza por la aplicación (ADR 002).
"""

import datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    MetaData,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ESQUEMA = "catalogo_medicos"

# Nombres fijos para las restricciones: Alembic puede manejarlas y los errores
# de PostgreSQL indican qué regla se violó.
CONVENCION_NOMBRES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Instantes que ocupa una franja: fecha + hora de inicio hasta fecha + hora de fin.
RANGO_FRANJA = text("tsrange(fecha + horario_inicio, fecha + horario_fin, '[)')")


class Base(DeclarativeBase):
    metadata = MetaData(schema=ESQUEMA, naming_convention=CONVENCION_NOMBRES)


class Especialidad(Base):
    __tablename__ = "especialidad"

    id_especialidad: Mapped[int] = mapped_column(Identity(), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True)
    descripcion: Mapped[str | None] = mapped_column(Text)


class Profesional(Base):
    __tablename__ = "profesional"
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_minusculas"),)

    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    matricula: Mapped[str] = mapped_column(String(30), unique=True)
    id_especialidad: Mapped[int] = mapped_column(
        ForeignKey(f"{ESQUEMA}.especialidad.id_especialidad", ondelete="RESTRICT")
    )
    # Copia de USUARIO.nombre y USUARIO.apellido, solo para mostrar (ADR 004).
    # El dato de verdad está en el servicio de usuarios.
    nombre: Mapped[str] = mapped_column(String(100))
    apellido: Mapped[str] = mapped_column(String(100))

    especialidad: Mapped[Especialidad] = relationship()


class Servicio(Base):
    __tablename__ = "servicio"
    __table_args__ = (
        UniqueConstraint("id_especialidad", "nombre", name="uq_servicio_especialidad_nombre"),
    )

    id_servicio: Mapped[int] = mapped_column(Identity(), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    id_especialidad: Mapped[int] = mapped_column(
        ForeignKey(f"{ESQUEMA}.especialidad.id_especialidad", ondelete="RESTRICT")
    )


class Disponibilidad(Base):
    __tablename__ = "disponibilidad"
    __table_args__ = (
        # Redundante con el EXCLUDE, pero figura en el modelo relacional.
        UniqueConstraint(
            "email_profesional", "fecha", "horario_inicio", name="uq_disponibilidad_franja"
        ),
        CheckConstraint("horario_inicio < horario_fin", name="horario_valido"),
        # Sin superposición: dos franjas del mismo profesional no pueden
        # compartir ningún instante. '[)' permite que una termine cuando
        # empieza la otra. Requiere btree_gist; solo existe en PostgreSQL.
        ExcludeConstraint(
            ("email_profesional", "="),
            (RANGO_FRANJA, "&&"),
            name="ex_disponibilidad_sin_superposicion",
            using="gist",
        ).ddl_if(dialect="postgresql"),
    )

    id_disponibilidad: Mapped[int] = mapped_column(Identity(), primary_key=True)
    email_profesional: Mapped[str] = mapped_column(
        String(254), ForeignKey(f"{ESQUEMA}.profesional.email", ondelete="RESTRICT")
    )
    fecha: Mapped[datetime.date] = mapped_column(Date)
    horario_inicio: Mapped[datetime.time] = mapped_column(Time)
    horario_fin: Mapped[datetime.time] = mapped_column(Time)
