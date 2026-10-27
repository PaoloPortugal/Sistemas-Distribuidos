"""Reglas de negocio de las disponibilidades (franjas horarias de un profesional).

Qué franjas están libres y si una se puede borrar depende de los turnos, que
viven en reservas: catálogo le pregunta (ADR 003). No existe modificar una
franja: se borra y se crea otra.
"""

import datetime
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clientes.reservas import ClienteReservas, DisponibilidadConTurno, ReservasNoDisponible
from app.db.modelos import Disponibilidad, Profesional
from app.dominio.profesionales import normalizar_email

DIAS_POR_DEFECTO = 30
DIAS_MAXIMOS = 90

registro = logging.getLogger(__name__)


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


class DisponibilidadNoEncontrada(Exception):
    pass


class DisponibilidadAjena(Exception):
    """La franja es de otro profesional."""


class FranjaYaEmpezo(Exception):
    pass


def obtener_propiedad(
    sesion: Session, id_disponibilidad: int, email_profesional: str
) -> Disponibilidad:
    disponibilidad = sesion.get(Disponibilidad, id_disponibilidad)
    if disponibilidad is None:
        raise DisponibilidadNoEncontrada
    if disponibilidad.email_profesional != normalizar_email(email_profesional):
        raise DisponibilidadAjena
    return disponibilidad


def modificar_disponibilidad(
    sesion: Session,
    *,
    id_disponibilidad: int,
    email_profesional: str,
    fecha: datetime.date,
    horario_inicio: datetime.time,
    horario_fin: datetime.time,
    ahora: datetime.datetime,
) -> Disponibilidad:
    disponibilidad = obtener_propiedad(sesion, id_disponibilidad, email_profesional)
    if horario_inicio >= horario_fin:
        raise HorarioInvalido
    if datetime.datetime.combine(fecha, horario_inicio) <= ahora:
        raise FranjaEnElPasado
    disponibilidad.fecha = fecha
    disponibilidad.horario_inicio = horario_inicio
    disponibilidad.horario_fin = horario_fin
    try:
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        existente = _franja_que_se_superpone(
            sesion, disponibilidad.email_profesional, fecha, horario_inicio, horario_fin
        )
        if existente is not None and existente.id_disponibilidad != id_disponibilidad:
            raise FranjaSuperpuesta(existente) from None
        raise
    return disponibilidad


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


def marcar_libres(
    disponibilidades: list[Disponibilidad], reservas: ClienteReservas, ahora: datetime.datetime
) -> list[tuple[Disponibilidad, bool | None]]:
    """Cada franja con `libre`: no empezó y no tiene turno RESERVADO ni bloqueo.

    Si reservas no responde, las que no empezaron quedan con `libre` = None
    (no se sabe); reservas igual rechaza la reserva de una franja tomada.
    """
    futuras = [d.id_disponibilidad for d in disponibilidades if not _empezo(d, ahora)]
    ocupadas: set[int] | None = set()
    if futuras:
        try:
            ocupadas = reservas.ocupadas(futuras)
        except ReservasNoDisponible as error:
            registro.warning("No se pudo consultar a reservas (%s); franjas sin marcar", error)
            ocupadas = None
    marcadas = []
    for d in disponibilidades:
        if _empezo(d, ahora):
            libre = False
        elif ocupadas is None:
            libre = None
        else:
            libre = d.id_disponibilidad not in ocupadas
        marcadas.append((d, libre))
    return marcadas


def eliminar_disponibilidad(
    sesion: Session,
    reservas: ClienteReservas,
    *,
    id_disponibilidad: int,
    email_profesional: str,
    ahora: datetime.datetime,
) -> None:
    """Borra una franja propia que no empezó y no tiene turno RESERVADO.

    Primero reservas la bloquea (y dice si tiene turno) y después se borra:
    una reserva que consultó a catálogo antes del borrado choca con el
    bloqueo, que queda para siempre. Si no se pudo borrar, se desbloquea. El
    FOR UPDATE impide que dos borrados de la misma franja se crucen.
    """
    disponibilidad = sesion.scalar(
        select(Disponibilidad)
        .where(Disponibilidad.id_disponibilidad == id_disponibilidad)
        .with_for_update()
    )
    if disponibilidad is None:
        sesion.rollback()
        raise DisponibilidadNoEncontrada
    if disponibilidad.email_profesional != normalizar_email(email_profesional):
        sesion.rollback()
        raise DisponibilidadAjena
    if _empezo(disponibilidad, ahora):
        sesion.rollback()
        raise FranjaYaEmpezo

    try:
        reservas.bloquear(id_disponibilidad)
    except DisponibilidadConTurno:
        sesion.rollback()
        raise
    except ReservasNoDisponible:
        # Pudo haberse aplicado (timeout de lectura): se compensa igual.
        _desbloquear_sin_fallar(reservas, id_disponibilidad)
        sesion.rollback()
        raise

    sesion.delete(disponibilidad)
    try:
        sesion.commit()
    except Exception:
        sesion.rollback()
        _desbloquear_sin_fallar(reservas, id_disponibilidad)
        raise


def _desbloquear_sin_fallar(reservas: ClienteReservas, id_disponibilidad: int) -> None:
    try:
        reservas.desbloquear(id_disponibilidad)
    except ReservasNoDisponible as error:
        # La franja sigue en catálogo pero no se puede reservar; repetir el
        # borrado la destraba (bloquear es idempotente).
        registro.error(
            "Posible inconsistencia: la franja %s pudo quedar bloqueada en reservas sin borrarse (%s)",
            id_disponibilidad,
            error,
        )


def _empezo(disponibilidad: Disponibilidad, ahora: datetime.datetime) -> bool:
    return datetime.datetime.combine(disponibilidad.fecha, disponibilidad.horario_inicio) <= ahora


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
