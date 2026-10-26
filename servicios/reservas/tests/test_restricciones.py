"""Restricciones de TURNO en la base: los CHECK y el índice único parcial.

Se insertan filas directamente, sin pasar por el dominio, para comprobar que
la base las rechaza por sí misma.
"""

import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.modelos import Turno

CREADO = datetime.datetime(2026, 11, 2, 13, 0, tzinfo=datetime.UTC)


def turno(**cambios) -> Turno:
    datos = {
        "email_paciente": "ana@ejemplo.com",
        "id_disponibilidad": 7,
        "id_servicio": 1,
        "estado": "RESERVADO",
        "fecha_creacion": CREADO,
        "email_profesional": "dr.gomez@ejemplo.com",
        "fecha": datetime.date(2026, 11, 5),
        "horario_inicio": datetime.time(9, 0),
        "horario_fin": datetime.time(9, 30),
    }
    return Turno(**(datos | cambios))


def cancelado(**cambios) -> dict:
    return {
        "estado": "CANCELADO",
        "fecha_cancelacion": CREADO + datetime.timedelta(hours=1),
        "cancelado_por": "PACIENTE",
    } | cambios


def guardar(fabrica_sesiones, *turnos: Turno) -> None:
    with fabrica_sesiones() as sesion:
        sesion.add_all(turnos)
        sesion.commit()


@pytest.mark.parametrize(
    "cambios",
    [
        {"estado": "RESERVADO"},
        cancelado(),
        cancelado(motivo_cancelacion="Viaje", cancelado_por="PROFESIONAL"),
        {"estado": "FINALIZADO"},
    ],
    ids=["reservado", "cancelado-sin-motivo", "cancelado-con-motivo", "finalizado"],
)
def test_filas_validas(fabrica_sesiones, cambios):
    guardar(fabrica_sesiones, turno(**cambios))


@pytest.mark.parametrize(
    ("cambios", "restriccion"),
    [
        ({"estado": "PENDIENTE"}, "estado_valido"),
        (cancelado(cancelado_por="ADMIN"), "cancelado_por_valido"),
        (cancelado(fecha_cancelacion=None), "cancelacion_coherente"),
        (cancelado(cancelado_por=None), "cancelacion_coherente"),
        ({"motivo_cancelacion": "Viaje"}, "cancelacion_coherente"),
        ({"fecha_cancelacion": CREADO}, "cancelacion_coherente"),
        ({"cancelado_por": "PACIENTE"}, "cancelacion_coherente"),
        ({"estado": "FINALIZADO", "cancelado_por": "PACIENTE"}, "cancelacion_coherente"),
        (cancelado(fecha_cancelacion=CREADO - datetime.timedelta(minutes=1)), "cancelacion_posterior"),
        ({"email_paciente": "Ana@Ejemplo.com"}, "email_paciente_minusculas"),
    ],
    ids=[
        "estado-invalido",
        "cancelado-por-invalido",
        "cancelado-sin-fecha",
        "cancelado-sin-quien",
        "reservado-con-motivo",
        "reservado-con-fecha-cancelacion",
        "reservado-con-quien",
        "finalizado-con-quien",
        "cancelacion-antes-de-creacion",
        "email-con-mayusculas",
    ],
)
def test_check_rechaza(fabrica_sesiones, cambios, restriccion):
    with pytest.raises(IntegrityError, match=restriccion):
        guardar(fabrica_sesiones, turno(**cambios))


def test_dos_reservados_en_la_misma_franja_se_rechazan(fabrica_sesiones):
    guardar(fabrica_sesiones, turno())

    with pytest.raises(IntegrityError, match="id_disponibilidad"):
        guardar(fabrica_sesiones, turno(email_paciente="beto@ejemplo.com"))


def test_cancelados_y_un_reservado_en_la_misma_franja_conviven(fabrica_sesiones):
    guardar(
        fabrica_sesiones,
        turno(**cancelado()),
        turno(email_paciente="beto@ejemplo.com", **cancelado()),
        turno(email_paciente="carla@ejemplo.com"),
    )


def test_reservados_en_franjas_distintas_conviven(fabrica_sesiones):
    guardar(fabrica_sesiones, turno(), turno(id_disponibilidad=8))
