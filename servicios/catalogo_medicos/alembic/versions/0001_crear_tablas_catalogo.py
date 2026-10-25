"""Crear tablas especialidad, profesional, servicio y disponibilidad

Revisión: 0001
Anterior:
Fecha: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ESQUEMA = "catalogo_medicos"

FALTA_BTREE_GIST = (
    "Falta la extensión btree_gist, necesaria para impedir disponibilidades "
    "superpuestas. El usuario del servicio no puede crearla. Con una base ya "
    "inicializada, crearla como superusuario:\n"
    '  docker compose exec postgres psql -U postgres -d turnos -c "CREATE EXTENSION IF NOT EXISTS btree_gist"\n'
    "o recrear la base con docker compose down -v (borra los datos)."
)


def upgrade() -> None:
    conexion = op.get_bind()
    if not conexion.scalar(sa.text("SELECT 1 FROM pg_extension WHERE extname = 'btree_gist'")):
        raise RuntimeError(FALTA_BTREE_GIST)

    op.create_table(
        "especialidad",
        sa.Column("id_especialidad", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id_especialidad", name=op.f("pk_especialidad")),
        sa.UniqueConstraint("nombre", name=op.f("uq_especialidad_nombre")),
        schema=ESQUEMA,
    )
    op.create_table(
        "profesional",
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("matricula", sa.String(30), nullable=False),
        sa.Column("id_especialidad", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("email", name=op.f("pk_profesional")),
        sa.CheckConstraint(
            "email = lower(email)", name=op.f("ck_profesional_email_minusculas")
        ),
        sa.UniqueConstraint("matricula", name=op.f("uq_profesional_matricula")),
        sa.ForeignKeyConstraint(
            ["id_especialidad"],
            [f"{ESQUEMA}.especialidad.id_especialidad"],
            name=op.f("fk_profesional_id_especialidad_especialidad"),
            ondelete="RESTRICT",
        ),
        schema=ESQUEMA,
    )
    op.create_table(
        "servicio",
        sa.Column("id_servicio", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("id_especialidad", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id_servicio", name=op.f("pk_servicio")),
        sa.UniqueConstraint(
            "id_especialidad", "nombre", name=op.f("uq_servicio_especialidad_nombre")
        ),
        sa.ForeignKeyConstraint(
            ["id_especialidad"],
            [f"{ESQUEMA}.especialidad.id_especialidad"],
            name=op.f("fk_servicio_id_especialidad_especialidad"),
            ondelete="RESTRICT",
        ),
        schema=ESQUEMA,
    )
    op.create_table(
        "disponibilidad",
        sa.Column("id_disponibilidad", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("email_profesional", sa.String(254), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("horario_inicio", sa.Time(), nullable=False),
        sa.Column("horario_fin", sa.Time(), nullable=False),
        sa.PrimaryKeyConstraint("id_disponibilidad", name=op.f("pk_disponibilidad")),
        sa.UniqueConstraint(
            "email_profesional",
            "fecha",
            "horario_inicio",
            name=op.f("uq_disponibilidad_franja"),
        ),
        sa.CheckConstraint(
            "horario_inicio < horario_fin", name=op.f("ck_disponibilidad_horario_valido")
        ),
        postgresql.ExcludeConstraint(
            ("email_profesional", "="),
            (sa.text("tsrange(fecha + horario_inicio, fecha + horario_fin, '[)')"), "&&"),
            name=op.f("ex_disponibilidad_sin_superposicion"),
            using="gist",
        ),
        sa.ForeignKeyConstraint(
            ["email_profesional"],
            [f"{ESQUEMA}.profesional.email"],
            name=op.f("fk_disponibilidad_email_profesional_profesional"),
            ondelete="RESTRICT",
        ),
        schema=ESQUEMA,
    )


def downgrade() -> None:
    op.drop_table("disponibilidad", schema=ESQUEMA)
    op.drop_table("servicio", schema=ESQUEMA)
    op.drop_table("profesional", schema=ESQUEMA)
    op.drop_table("especialidad", schema=ESQUEMA)
