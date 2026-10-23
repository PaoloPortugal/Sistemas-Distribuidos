"""Modelos de persistencia del servicio de usuarios (esquema `usuarios`)."""

from sqlalchemy import CheckConstraint, ForeignKey, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ESQUEMA = "usuarios"

# Nombres fijos para las restricciones: Alembic puede manejarlas y los errores
# de PostgreSQL indican qué regla se violó.
CONVENCION_NOMBRES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(schema=ESQUEMA, naming_convention=CONVENCION_NOMBRES)


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = (
        CheckConstraint("tipo IN ('PACIENTE', 'PROFESIONAL')", name="tipo_valido"),
        CheckConstraint("email = lower(email)", name="email_minusculas"),
    )

    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    contrasena_hash: Mapped[str] = mapped_column(String(255))
    nombre: Mapped[str] = mapped_column(String(100))
    apellido: Mapped[str] = mapped_column(String(100))
    tipo: Mapped[str] = mapped_column(String(20))

    # El borrado en cascada lo hace PostgreSQL (ON DELETE CASCADE).
    paciente: Mapped["Paciente | None"] = relationship(
        back_populates="usuario", passive_deletes=True
    )


class Paciente(Base):
    __tablename__ = "paciente"

    email: Mapped[str] = mapped_column(
        String(254),
        ForeignKey(f"{ESQUEMA}.usuario.email", ondelete="CASCADE"),
        primary_key=True,
    )
    documento: Mapped[str] = mapped_column(String(20), unique=True)
    telefono: Mapped[str | None] = mapped_column(String(30))

    usuario: Mapped[Usuario] = relationship(back_populates="paciente")
