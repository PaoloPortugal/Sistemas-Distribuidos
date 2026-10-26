"""Copiar nombre y apellido en profesional

Copia desnormalizada de USUARIO.nombre y USUARIO.apellido, solo para mostrar
el listado de profesionales sin consultar al servicio de usuarios (ADR 004).

Revisión: 0003
Anterior: 0002
Fecha: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ESQUEMA = "catalogo_medicos"


def upgrade() -> None:
    # Las filas que ya existan quedan con texto vacío; el valor por defecto se
    # quita enseguida para que las altas nuevas tengan que mandarlos.
    for columna in ("nombre", "apellido"):
        op.add_column(
            "profesional",
            sa.Column(columna, sa.String(100), nullable=False, server_default=""),
            schema=ESQUEMA,
        )
        op.alter_column("profesional", columna, server_default=None, schema=ESQUEMA)


def downgrade() -> None:
    op.drop_column("profesional", "apellido", schema=ESQUEMA)
    op.drop_column("profesional", "nombre", schema=ESQUEMA)
