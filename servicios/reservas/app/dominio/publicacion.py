"""Publicación de los eventos del outbox (ADR 005).

Cada evento se publica en su propia transacción: se toma con
`FOR UPDATE SKIP LOCKED` (otra réplica del publicador no lo toma), se publica,
y `publicado_en` se completa **solo si el broker confirmó**. Si el proceso se
cae entre la confirmación y el commit, el evento se vuelve a publicar: la
entrega es "al menos una vez" y el consumidor descarta duplicados por
`id_evento`.

Mientras publica un evento, el correlation_id del contexto es el que el evento
trae del pedido que lo originó, así los logs del publicador lo incluyen.
"""

import asyncio
import datetime
import logging
from collections.abc import Callable
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.modelos import EventoSaliente
from app.observabilidad import con_correlation_id

registro = logging.getLogger(__name__)


class Publicador(Protocol):
    async def publicar(self, evento: EventoSaliente) -> None:
        """Publica y espera la confirmación del broker; si no la hay, lanza una excepción."""


def _siguiente_pendiente(sesion: Session) -> EventoSaliente | None:
    consulta = (
        select(EventoSaliente)
        .where(EventoSaliente.publicado_en.is_(None))
        .order_by(EventoSaliente.creado_en, EventoSaliente.id_evento)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    return sesion.scalars(consulta).first()


async def publicar_pendientes(
    fabrica_sesiones: Callable[[], Session],
    publicador: Publicador,
    *,
    lote: int,
    ahora: Callable[[], datetime.datetime],
    pausa: float = 0.0,
) -> int:
    """Publica hasta `lote` eventos pendientes, en orden de creación.

    Devuelve cuántos publicó. Si una publicación no se confirma, la excepción
    sube sin marcar ese evento (queda pendiente para el próximo intento).
    `pausa` limita el ritmo (segundos entre eventos); por defecto no hay pausa.
    """
    publicados = 0
    while publicados < lote:
        with fabrica_sesiones() as sesion:
            evento = _siguiente_pendiente(sesion)
            if evento is None:
                break
            with con_correlation_id(evento.payload.get("correlation_id")):
                await publicador.publicar(evento)  # espera la confirmación del broker
                evento.publicado_en = ahora()
                sesion.commit()
                registro.info(
                    "Evento %s %s publicado",
                    evento.tipo,
                    evento.id_evento,
                    extra={
                        "id_evento": str(evento.id_evento),
                        "tipo_evento": evento.tipo,
                        "id_turno": evento.payload.get("id_turno"),
                    },
                )
        publicados += 1
        if pausa:
            await asyncio.sleep(pausa)
    return publicados
