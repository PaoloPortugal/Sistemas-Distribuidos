"""Crear tablas turno y evento_saliente (outbox)

Revisión: 0001
Anterior:
Fecha: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ESQUEMA = "reservas"


def upgrade() -> None:
    op.create_table(
        "turno",
        sa.Column("id_turno", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("email_paciente", sa.String(254), nullable=False),
        sa.Column("id_disponibilidad", sa.Integer(), nullable=False),
        sa.Column("id_servicio", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("fecha_creacion", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fecha_cancelacion", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_cancelacion", sa.String(500), nullable=True),
        sa.Column("cancelado_por", sa.String(20), nullable=True),
        # Copia de la disponibilidad al reservar (ADR 006).
        sa.Column("email_profesional", sa.String(254), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("horario_inicio", sa.Time(), nullable=False),
        sa.Column("horario_fin", sa.Time(), nullable=False),
        sa.PrimaryKeyConstraint("id_turno", name=op.f("pk_turno")),
        sa.CheckConstraint(
            "estado IN ('RESERVADO', 'CANCELADO', 'FINALIZADO')",
            name=op.f("ck_turno_estado_valido"),
        ),
        sa.CheckConstraint(
            "cancelado_por IN ('PACIENTE', 'PROFESIONAL')",
            name=op.f("ck_turno_cancelado_por_valido"),
        ),
        sa.CheckConstraint(
            "(estado = 'CANCELADO' AND fecha_cancelacion IS NOT NULL AND cancelado_por IS NOT NULL)"
            " OR (estado <> 'CANCELADO' AND fecha_cancelacion IS NULL"
            " AND motivo_cancelacion IS NULL AND cancelado_por IS NULL)",
            name=op.f("ck_turno_cancelacion_coherente"),
        ),
        sa.CheckConstraint(
            "fecha_cancelacion >= fecha_creacion", name=op.f("ck_turno_cancelacion_posterior")
        ),
        sa.CheckConstraint(
            "email_paciente = lower(email_paciente)",
            name=op.f("ck_turno_email_paciente_minusculas"),
        ),
        schema=ESQUEMA,
    )
    # Regla clave contra la doble reserva: un solo turno RESERVADO por disponibilidad.
    op.create_index(
        "ux_turno_disponibilidad_reservada",
        "turno",
        ["id_disponibilidad"],
        unique=True,
        schema=ESQUEMA,
        postgresql_where=sa.text("estado = 'RESERVADO'"),
    )
    op.create_index("ix_turno_email_paciente", "turno", ["email_paciente"], schema=ESQUEMA)
    op.create_index(
        "ix_turno_profesional_fecha", "turno", ["email_profesional", "fecha"], schema=ESQUEMA
    )

    op.create_table(
        "evento_saliente",
        sa.Column("id_evento", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("publicado_en", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id_evento", name=op.f("pk_evento_saliente")),
        sa.CheckConstraint(
            "tipo IN ('turno.confirmado', 'turno.cancelado')",
            name=op.f("ck_evento_saliente_tipo_valido"),
        ),
        schema=ESQUEMA,
    )
    op.create_index(
        "ix_evento_saliente_pendiente",
        "evento_saliente",
        ["creado_en"],
        schema=ESQUEMA,
        postgresql_where=sa.text("publicado_en IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("evento_saliente", schema=ESQUEMA)
    op.drop_table("turno", schema=ESQUEMA)
