"""Crear notificacion, envio_mail y evento_procesado

Revisión: 0001
Anterior:
Fecha: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ESQUEMA = "notificaciones"


def upgrade() -> None:
    op.create_table(
        "notificacion",
        sa.Column("id_notificacion", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("id_turno", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("estado_notificacion", sa.String(20), nullable=False),
        sa.Column("destinatario", sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint("id_notificacion", name=op.f("pk_notificacion")),
        sa.CheckConstraint(
            "tipo IN ('CONFIRMADO', 'CANCELADO')", name=op.f("ck_notificacion_tipo_valido")
        ),
        sa.CheckConstraint(
            "estado_notificacion IN ('PENDIENTE', 'ENVIADO', 'FALLIDO')",
            name=op.f("ck_notificacion_estado_valido"),
        ),
        sa.CheckConstraint(
            "destinatario IN ('PACIENTE', 'PROFESIONAL')",
            name=op.f("ck_notificacion_destinatario_valido"),
        ),
        sa.UniqueConstraint(
            "id_turno",
            "tipo",
            "destinatario",
            name=op.f("uq_notificacion_turno_tipo_destinatario"),
        ),
        schema=ESQUEMA,
    )
    op.create_table(
        "envio_mail",
        sa.Column("id_notificacion", sa.Integer(), nullable=False),
        sa.Column("email_destinatario", sa.String(254), nullable=False),
        sa.Column("asunto", sa.String(200), nullable=False),
        sa.Column("cuerpo", sa.Text(), nullable=False),
        sa.Column("intentos", sa.Integer(), nullable=False),
        sa.Column("proximo_intento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ultimo_error", sa.Text(), nullable=True),
        sa.Column("enviado_en", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id_notificacion", name=op.f("pk_envio_mail")),
        sa.CheckConstraint("intentos >= 0", name=op.f("ck_envio_mail_intentos_no_negativos")),
        sa.ForeignKeyConstraint(
            ["id_notificacion"],
            [f"{ESQUEMA}.notificacion.id_notificacion"],
            name=op.f("fk_envio_mail_id_notificacion_notificacion"),
            ondelete="CASCADE",
        ),
        schema=ESQUEMA,
    )
    op.create_index(
        "ix_envio_mail_proximo_intento", "envio_mail", ["proximo_intento"], schema=ESQUEMA
    )
    op.create_table(
        "evento_procesado",
        sa.Column("id_evento", sa.Uuid(), nullable=False),
        sa.Column("recibido_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id_evento", name=op.f("pk_evento_procesado")),
        schema=ESQUEMA,
    )


def downgrade() -> None:
    op.drop_table("evento_procesado", schema=ESQUEMA)
    op.drop_table("envio_mail", schema=ESQUEMA)
    op.drop_table("notificacion", schema=ESQUEMA)
