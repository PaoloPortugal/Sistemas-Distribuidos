"""Datos iniciales: especialidades y servicios

El MER no tiene un rol administrador que las cargue, así que se crean con
esta migración. id_especialidad = 1 tiene que existir (lo usan los ejemplos
de registro de profesional).

Revisión: 0002
Anterior: 0001
Fecha: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ESQUEMA = "catalogo_medicos"

ESPECIALIDADES = [
    (1, "Clínica médica", "Atención integral del adulto y derivación a especialistas."),
    (2, "Pediatría", "Atención de niños y adolescentes."),
    (3, "Cardiología", "Diagnóstico y tratamiento de enfermedades del corazón."),
    (4, "Dermatología", "Diagnóstico y tratamiento de enfermedades de la piel."),
]

SERVICIOS = {
    1: ["Consulta general", "Control preventivo", "Certificado de aptitud física"],
    2: ["Control del niño sano", "Consulta por enfermedad"],
    3: ["Consulta cardiológica", "Electrocardiograma", "Ecocardiograma"],
    4: ["Consulta dermatológica", "Control de lunares"],
}

especialidad = sa.table(
    "especialidad",
    sa.column("id_especialidad", sa.Integer),
    sa.column("nombre", sa.String),
    sa.column("descripcion", sa.Text),
    schema=ESQUEMA,
)
servicio = sa.table(
    "servicio",
    sa.column("nombre", sa.String),
    sa.column("id_especialidad", sa.Integer),
    schema=ESQUEMA,
)


def upgrade() -> None:
    op.bulk_insert(
        especialidad,
        [
            {"id_especialidad": id_, "nombre": nombre, "descripcion": descripcion}
            for id_, nombre, descripcion in ESPECIALIDADES
        ],
    )
    # Los ids se insertaron explícitos: la identidad sigue desde el mayor.
    op.execute(
        f"SELECT setval(pg_get_serial_sequence('{ESQUEMA}.especialidad', 'id_especialidad'), "
        f"(SELECT max(id_especialidad) FROM {ESQUEMA}.especialidad))"
    )
    op.bulk_insert(
        servicio,
        [
            {"nombre": nombre, "id_especialidad": id_especialidad}
            for id_especialidad, nombres in SERVICIOS.items()
            for nombre in nombres
        ],
    )


def downgrade() -> None:
    ids = [id_ for id_, _, _ in ESPECIALIDADES]
    op.execute(servicio.delete().where(servicio.c.id_especialidad.in_(ids)))
    op.execute(especialidad.delete().where(especialidad.c.id_especialidad.in_(ids)))
