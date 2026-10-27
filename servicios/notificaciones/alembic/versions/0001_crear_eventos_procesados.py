"""Crear tabla de eventos procesados

Revisión: 0001
Anterior:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evento_procesado",
        sa.Column("id_evento", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.String(50), nullable=False),
        sa.Column("procesado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id_evento", name="pk_evento_procesado"),
        schema="notificaciones",
    )


def downgrade() -> None:
    op.drop_table("evento_procesado", schema="notificaciones")
