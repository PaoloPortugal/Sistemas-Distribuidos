"""Crear tablas usuario y paciente

Revisión: 0001
Anterior:
Fecha: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ESQUEMA = "usuarios"


def upgrade() -> None:
    op.create_table(
        "usuario",
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("contrasena_hash", sa.String(255), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("apellido", sa.String(100), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint("email", name=op.f("pk_usuario")),
        sa.CheckConstraint(
            "tipo IN ('PACIENTE', 'PROFESIONAL')", name=op.f("ck_usuario_tipo_valido")
        ),
        sa.CheckConstraint(
            "email = lower(email)", name=op.f("ck_usuario_email_minusculas")
        ),
        schema=ESQUEMA,
    )
    op.create_table(
        "paciente",
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("documento", sa.String(20), nullable=False),
        sa.Column("telefono", sa.String(30), nullable=True),
        sa.PrimaryKeyConstraint("email", name=op.f("pk_paciente")),
        sa.ForeignKeyConstraint(
            ["email"],
            [f"{ESQUEMA}.usuario.email"],
            name=op.f("fk_paciente_email_usuario"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("documento", name=op.f("uq_paciente_documento")),
        schema=ESQUEMA,
    )


def downgrade() -> None:
    op.drop_table("paciente", schema=ESQUEMA)
    op.drop_table("usuario", schema=ESQUEMA)
