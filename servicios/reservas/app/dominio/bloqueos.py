"""Horarios ocupados y bloqueo de horarios que catálogo va a borrar (ADR 003).

Bloquear y reservar el mismo horario no pueden cruzarse: bloquear toma un
lock exclusivo por `id_disponibilidad` y reservar uno compartido
(`pg_advisory_xact_lock`), los dos dentro de su transacción. Así bloquear ve
el turno de una reserva que ya empezó, y reservar ve el bloqueo de un borrado
que ya empezó. Dos reservas del mismo horario sí corren a la vez: entre ellas
decide el índice único parcial.
"""

import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.modelos import RESERVADO, DisponibilidadBloqueada, Turno

# Primer número de la clave del advisory lock: separa estos locks de otros
# que use la base. El segundo es el id_disponibilidad.
CLASE_LOCK_DISPONIBILIDAD = 3
MAXIMO_IDS = 5000


class DisponibilidadConTurno(Exception):
    """El horario tiene un turno RESERVADO: no se puede borrar."""


def tomar_lock(sesion: Session, id_disponibilidad: int, *, exclusivo: bool) -> None:
    """Lock de la transacción sobre el horario. SQLite (tests) no lo tiene."""
    if sesion.get_bind().dialect.name != "postgresql":
        return
    funcion = func.pg_advisory_xact_lock if exclusivo else func.pg_advisory_xact_lock_shared
    sesion.execute(select(funcion(CLASE_LOCK_DISPONIBILIDAD, id_disponibilidad)))


def esta_bloqueada(sesion: Session, id_disponibilidad: int) -> bool:
    return sesion.get(DisponibilidadBloqueada, id_disponibilidad) is not None


def ocupadas(sesion: Session, ids: list[int]) -> list[int]:
    """Los ids con un turno RESERVADO o bloqueados, ordenados."""
    if not ids:
        return []
    reservadas = select(Turno.id_disponibilidad).where(
        Turno.id_disponibilidad.in_(ids), Turno.estado == RESERVADO
    )
    bloqueadas = select(DisponibilidadBloqueada.id_disponibilidad).where(
        DisponibilidadBloqueada.id_disponibilidad.in_(ids)
    )
    return sorted(set(sesion.scalars(reservadas)) | set(sesion.scalars(bloqueadas)))


def bloquear(sesion: Session, id_disponibilidad: int, ahora: datetime.datetime) -> None:
    """Bloquea el horario si no tiene turno RESERVADO. Repetirlo no cambia nada."""
    tomar_lock(sesion, id_disponibilidad, exclusivo=True)
    reservado = sesion.scalar(
        select(Turno.id_turno).where(
            Turno.id_disponibilidad == id_disponibilidad, Turno.estado == RESERVADO
        )
    )
    if reservado is not None:
        sesion.rollback()
        raise DisponibilidadConTurno
    if not esta_bloqueada(sesion, id_disponibilidad):
        sesion.add(DisponibilidadBloqueada(id_disponibilidad=id_disponibilidad, bloqueada_en=ahora))
    sesion.commit()


def desbloquear(sesion: Session, id_disponibilidad: int) -> None:
    """Compensación de catálogo cuando no pudo borrar. Repetirlo no cambia nada."""
    sesion.execute(
        delete(DisponibilidadBloqueada).where(
            DisponibilidadBloqueada.id_disponibilidad == id_disponibilidad
        )
    )
    sesion.commit()
