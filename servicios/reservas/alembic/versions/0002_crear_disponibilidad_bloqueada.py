"""Crear tabla disponibilidad_bloqueada (ADR 003)

Revisión: 0002
Anterior: 0001
Fecha: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ESQUEMA = "reservas"


def upgrade() -> None:
    op.create_table(
        "disponibilidad_bloqueada",
        sa.Column("id_disponibilidad", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("bloqueada_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id_disponibilidad", name=op.f("pk_disponibilidad_bloqueada")),
        schema=ESQUEMA,
    )


def downgrade() -> None:
    op.drop_table("disponibilidad_bloqueada", schema=ESQUEMA)
