"""Consultas del catálogo: especialidades, servicios y profesionales."""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.modelos import Disponibilidad, Especialidad, Profesional, Servicio
from app.dominio.profesionales import normalizar_email


class EspecialidadNoEncontrada(Exception):
    pass


class DisponibilidadNoEncontrada(Exception):
    pass


class ServicioNoEncontrado(Exception):
    pass


def datos_para_reservar(
    sesion: Session, id_disponibilidad: int, id_servicio: int
) -> tuple[Disponibilidad, int, Servicio]:
    """Franja, especialidad de su profesional y servicio pedido, para reservas.

    Catálogo solo informa: las reglas (coherencia del servicio, franja en el
    pasado) las aplica reservas.
    """
    disponibilidad = sesion.get(Disponibilidad, id_disponibilidad)
    if disponibilidad is None:
        raise DisponibilidadNoEncontrada
    servicio = sesion.get(Servicio, id_servicio)
    if servicio is None:
        raise ServicioNoEncontrado
    profesional = sesion.get(Profesional, disponibilidad.email_profesional)
    return disponibilidad, profesional.id_especialidad, servicio


def listar_especialidades(sesion: Session) -> list[Especialidad]:
    return list(sesion.scalars(select(Especialidad).order_by(Especialidad.nombre)))


def listar_servicios(sesion: Session, id_especialidad: int) -> list[Servicio]:
    _exigir_especialidad(sesion, id_especialidad)
    consulta = (
        select(Servicio)
        .where(Servicio.id_especialidad == id_especialidad)
        .order_by(Servicio.nombre)
    )
    return list(sesion.scalars(consulta))


def listar_profesionales(sesion: Session, id_especialidad: int | None = None) -> list[Profesional]:
    consulta = (
        select(Profesional)
        .options(joinedload(Profesional.especialidad))
        .order_by(Profesional.apellido, Profesional.nombre, Profesional.email)
    )
    if id_especialidad is not None:
        _exigir_especialidad(sesion, id_especialidad)
        consulta = consulta.where(Profesional.id_especialidad == id_especialidad)
    return list(sesion.scalars(consulta))


def obtener_profesional(sesion: Session, email: str) -> Profesional | None:
    return sesion.get(Profesional, normalizar_email(email))


def _exigir_especialidad(sesion: Session, id_especialidad: int) -> None:
    if sesion.get(Especialidad, id_especialidad) is None:
        raise EspecialidadNoEncontrada
