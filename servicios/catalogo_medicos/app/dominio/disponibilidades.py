"""Reglas de negocio de las disponibilidades (franjas horarias de un profesional).

Pendientes (ADR 003): marcar qué franjas están libres y borrar una franja
dependen de los turnos, que viven en reservas.
"""

import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.modelos import Disponibilidad, Profesional
from app.dominio.profesionales import normalizar_email

DIAS_POR_DEFECTO = 30
DIAS_MAXIMOS = 90


class HorarioInvalido(Exception):
    pass


class FranjaEnElPasado(Exception):
    pass


class ProfesionalNoRegistrado(Exception):
    """El token es de un profesional que no está en el catálogo."""


class FranjaSuperpuesta(Exception):
    def __init__(self, existente: Disponibilidad):
        super().__init__(existente)
        self.existente = existente


class RangoInvalido(Exception):
    pass


def crear_disponibilidad(
    sesion: Session,
    *,
    email_profesional: str,
    fecha: datetime.date,
    horario_inicio: datetime.time,
    horario_fin: datetime.time,
    ahora: datetime.datetime,
) -> Disponibilidad:
    """Crea una franja del profesional.

    La superposición la detecta PostgreSQL (EXCLUDE USING gist), no una
    consulta previa: así dos pedidos simultáneos no pueden pasar los dos.
    """
    if horario_inicio >= horario_fin:
        raise HorarioInvalido
    if datetime.datetime.combine(fecha, horario_inicio) <= ahora:
        raise FranjaEnElPasado

    email = normalizar_email(email_profesional)
    disponibilidad = Disponibilidad(
        email_profesional=email,
        fecha=fecha,
        horario_inicio=horario_inicio,
        horario_fin=horario_fin,
    )
    sesion.add(disponibilidad)
    try:
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        existente = _franja_que_se_superpone(sesion, email, fecha, horario_inicio, horario_fin)
        if existente is not None:
            raise FranjaSuperpuesta(existente) from None
        if sesion.get(Profesional, email) is None:
            raise ProfesionalNoRegistrado from None
        raise
    return disponibilidad


def listar_disponibilidades(
    sesion: Session, email_profesional: str, desde: datetime.date, hasta: datetime.date
) -> list[Disponibilidad]:
    consulta = (
        select(Disponibilidad)
        .where(
            Disponibilidad.email_profesional == normalizar_email(email_profesional),
            Disponibilidad.fecha >= desde,
            Disponibilidad.fecha <= hasta,
        )
        .order_by(Disponibilidad.fecha, Disponibilidad.horario_inicio)
    )
    return list(sesion.scalars(consulta))


def resolver_rango(
    desde: datetime.date | None, hasta: datetime.date | None, hoy: datetime.date
) -> tuple[datetime.date, datetime.date]:
    """Completa el rango: por defecto desde hoy y 30 días; como máximo 90 días."""
    desde = desde or hoy
    hasta = hasta or desde + datetime.timedelta(days=DIAS_POR_DEFECTO)
    if desde > hasta:
        raise RangoInvalido("'desde' no puede ser posterior a 'hasta'")
    if (hasta - desde).days > DIAS_MAXIMOS:
        raise RangoInvalido(f"El rango no puede superar {DIAS_MAXIMOS} días")
    return desde, hasta


def _franja_que_se_superpone(
    sesion: Session,
    email: str,
    fecha: datetime.date,
    horario_inicio: datetime.time,
    horario_fin: datetime.time,
) -> Disponibilidad | None:
    consulta = select(Disponibilidad).where(
        Disponibilidad.email_profesional == email,
        Disponibilidad.fecha == fecha,
        Disponibilidad.horario_inicio < horario_fin,
        Disponibilidad.horario_fin > horario_inicio,
    )
    return sesion.scalars(consulta.limit(1)).first()
