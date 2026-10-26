"""Reglas de negocio de los turnos: reservar, cancelar y listar.

Reservas es la autoridad final sobre la doble reserva: la impide el índice
único parcial de PostgreSQL (un solo turno RESERVADO por disponibilidad).
Cada cambio de estado escribe su evento en el outbox, en la misma
transacción (ADR 005).
"""

import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clientes.catalogo import ClienteCatalogo
from app.db.modelos import (
    CANCELADO,
    PACIENTE,
    PROFESIONAL,
    RESERVADO,
    TURNO_CANCELADO,
    TURNO_CONFIRMADO,
    EventoSaliente,
    Turno,
)
from app.dominio import reloj

PLAZO_CANCELACION_PACIENTE = datetime.timedelta(hours=24)
DIAS_POR_DEFECTO = 30
DIAS_MAXIMOS = 90


class ServicioNoCorresponde(Exception):
    """El servicio no es de la especialidad del profesional de la franja."""


class FranjaEnElPasado(Exception):
    pass


class HorarioYaReservado(Exception):
    pass


class TurnoInexistente(Exception):
    pass


class TurnoAjeno(Exception):
    pass


class TurnoNoCancelable(Exception):
    """El turno ya no está RESERVADO (cancelado o finalizado)."""


class FueraDePlazo(Exception):
    """Paciente: faltan 24 h o menos. Profesional: el turno ya empezó (ADR 007)."""


class RangoInvalido(Exception):
    pass


def normalizar_email(email: str) -> str:
    return email.strip().lower()


def reservar(
    sesion: Session,
    catalogo: ClienteCatalogo,
    *,
    email_paciente: str,
    id_disponibilidad: int,
    id_servicio: int,
    ahora: datetime.datetime,
) -> Turno:
    """Reserva la franja para el paciente.

    Catálogo informa la franja y el servicio; las reglas se aplican acá. Si
    catálogo no responde, no se crea nada (las excepciones del cliente suben).
    """
    franja = catalogo.datos_para_reservar(id_disponibilidad, id_servicio)
    # Coherencia del servicio (modelo relacional): SERVICIO.id_especialidad =
    # PROFESIONAL.id_especialidad del dueño de la disponibilidad.
    if franja.id_especialidad_servicio != franja.id_especialidad:
        raise ServicioNoCorresponde
    if reloj.instante(franja.fecha, franja.horario_inicio) <= ahora:
        raise FranjaEnElPasado

    turno = Turno(
        email_paciente=normalizar_email(email_paciente),
        id_disponibilidad=franja.id_disponibilidad,
        id_servicio=franja.id_servicio,
        estado=RESERVADO,
        fecha_creacion=ahora,
        email_profesional=franja.email_profesional,
        fecha=franja.fecha,
        horario_inicio=franja.horario_inicio,
        horario_fin=franja.horario_fin,
    )
    sesion.add(turno)
    try:
        sesion.flush()  # asigna id_turno, que va en el evento
        sesion.add(_evento(TURNO_CONFIRMADO, turno, ahora))
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        if _franja_reservada(sesion, franja.id_disponibilidad):
            raise HorarioYaReservado from None
        raise
    return turno


def cancelar(
    sesion: Session,
    *,
    id_turno: int,
    email: str,
    tipo: str,
    motivo: str | None,
    ahora: datetime.datetime,
) -> Turno:
    """Cancela el turno; lo pueden hacer el paciente o el profesional dueños.

    Plazo según quién cancela (RNE del MER, ADR 007):
    - paciente: solo si ahora + 24 h < inicio del turno;
    - profesional: en cualquier momento antes del inicio.
    """
    # FOR UPDATE: dos cancelaciones simultáneas no pueden escribir dos eventos.
    turno = sesion.scalar(select(Turno).where(Turno.id_turno == id_turno).with_for_update())
    if turno is None:
        raise TurnoInexistente
    cancelado_por = _quien_cancela(turno, normalizar_email(email), tipo)
    if turno.estado != RESERVADO:
        raise TurnoNoCancelable

    inicio = reloj.instante(turno.fecha, turno.horario_inicio)
    if cancelado_por == PACIENTE and not ahora + PLAZO_CANCELACION_PACIENTE < inicio:
        raise FueraDePlazo
    if cancelado_por == PROFESIONAL and not ahora < inicio:
        raise FueraDePlazo

    turno.estado = CANCELADO
    turno.fecha_cancelacion = ahora
    turno.cancelado_por = cancelado_por
    turno.motivo_cancelacion = motivo
    sesion.add(_evento(TURNO_CANCELADO, turno, ahora))
    sesion.commit()
    return turno


def turnos_de_paciente(sesion: Session, email: str) -> list[Turno]:
    consulta = (
        select(Turno)
        .where(Turno.email_paciente == normalizar_email(email))
        .order_by(Turno.fecha, Turno.horario_inicio, Turno.id_turno)
    )
    return list(sesion.scalars(consulta))


def agenda(
    sesion: Session, email_profesional: str, desde: datetime.date, hasta: datetime.date
) -> list[Turno]:
    consulta = (
        select(Turno)
        .where(
            Turno.email_profesional == normalizar_email(email_profesional),
            Turno.fecha >= desde,
            Turno.fecha <= hasta,
        )
        .order_by(Turno.fecha, Turno.horario_inicio, Turno.id_turno)
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


def _quien_cancela(turno: Turno, email: str, tipo: str) -> str:
    if tipo == PACIENTE and turno.email_paciente == email:
        return PACIENTE
    if tipo == PROFESIONAL and turno.email_profesional == email:
        return PROFESIONAL
    raise TurnoAjeno


def _franja_reservada(sesion: Session, id_disponibilidad: int) -> bool:
    consulta = select(Turno.id_turno).where(
        Turno.id_disponibilidad == id_disponibilidad, Turno.estado == RESERVADO
    )
    return sesion.scalar(consulta) is not None


def _evento(tipo: str, turno: Turno, ahora: datetime.datetime) -> EventoSaliente:
    """Evento para el outbox; `id_evento` es el event_id que deduplica el consumidor."""
    id_evento = uuid.uuid4()
    payload = {
        "id_evento": str(id_evento),
        "tipo": tipo,
        "ocurrido_en": ahora.isoformat(),
        "id_turno": turno.id_turno,
        "id_disponibilidad": turno.id_disponibilidad,
        "id_servicio": turno.id_servicio,
        "email_paciente": turno.email_paciente,
        "email_profesional": turno.email_profesional,
        "fecha": turno.fecha.isoformat(),
        "horario_inicio": turno.horario_inicio.isoformat(),
        "horario_fin": turno.horario_fin.isoformat(),
    }
    if tipo == TURNO_CANCELADO:
        payload |= {"cancelado_por": turno.cancelado_por, "motivo": turno.motivo_cancelacion}
    return EventoSaliente(id_evento=id_evento, tipo=tipo, payload=payload, creado_en=ahora)
