"""Registro idempotente de un evento: dos NOTIFICACION en PENDIENTE (ADR 008).

En una sola transacción se insertan el `id_evento` en `evento_procesado`, las
dos NOTIFICACION (paciente y profesional) y sus dos `envio_mail`. Si el
evento ya se procesó, la PK de `evento_procesado` lo rechaza y no se crea
nada: el consumidor igual hace ack.
"""

import datetime
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.modelos import CANCELADO, CONFIRMADO, PENDIENTE, EnvioMail, EventoProcesado, Notificacion
from app.dominio.eventos import TURNO_CONFIRMADO, EventoTurno
from app.dominio.mensajes import armar_mails

registro = logging.getLogger(__name__)


def registrar_evento(sesion: Session, evento: EventoTurno, ahora: datetime.datetime) -> bool:
    """Crea las notificaciones del evento. Devuelve False si ya se había procesado."""
    tipo = CONFIRMADO if evento.tipo == TURNO_CONFIRMADO else CANCELADO
    sesion.add(EventoProcesado(id_evento=evento.id_evento, recibido_en=ahora))
    for mail in armar_mails(evento):
        notificacion = Notificacion(
            id_turno=evento.id_turno,
            tipo=tipo,
            estado_notificacion=PENDIENTE,
            destinatario=mail.destinatario,
        )
        notificacion.envio = EnvioMail(
            email_destinatario=mail.email,
            asunto=mail.asunto,
            cuerpo=mail.cuerpo,
            intentos=0,
            proximo_intento=ahora,
        )
        sesion.add(notificacion)
    try:
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        if sesion.get(EventoProcesado, evento.id_evento) is not None:
            return False  # el mismo evento llegó otra vez
        if _ya_notificado(sesion, evento.id_turno, tipo):
            # Otro evento con distinto id_evento ya avisó lo mismo: no se repite.
            registro.warning(
                "Turno %s ya tenía notificaciones %s; se ignora el evento %s",
                evento.id_turno, tipo, evento.id_evento,
            )
            return False
        raise
    return True


def _ya_notificado(sesion: Session, id_turno: int, tipo: str) -> bool:
    consulta = select(Notificacion.id_notificacion).where(
        Notificacion.id_turno == id_turno, Notificacion.tipo == tipo
    )
    return sesion.scalar(consulta.limit(1)) is not None
