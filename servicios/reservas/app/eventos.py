"""Publicación confiable del outbox de Reservas en RabbitMQ."""

import asyncio
import datetime
import json
import logging

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from sqlalchemy import select, update

from app.config import configuracion
from app.db.modelos import EventoSaliente
from app.db.sesion import obtener_fabrica_sesiones

logger = logging.getLogger(__name__)
EXCHANGE = "turnos"
TIPOS_EVENTO = ("turno.confirmado", "turno.cancelado")


async def ejecutar_publicador(stop: asyncio.Event) -> None:
    """Publica el outbox; si RabbitMQ cae, reintenta sin perder eventos."""
    while not stop.is_set():
        try:
            await _publicar_pendientes(stop)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("fallo_publicador_outbox")
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=configuracion.intervalo_publicador_segundos * 5
                )
            except asyncio.TimeoutError:
                pass


async def _publicar_pendientes(stop: asyncio.Event) -> None:
    connection = await aio_pika.connect_robust(configuracion.url_rabbitmq)
    try:
        channel = await connection.channel(publisher_confirms=True)
        exchange = await channel.declare_exchange(
            EXCHANGE, ExchangeType.TOPIC, durable=True
        )
        while not stop.is_set():
            eventos = await asyncio.to_thread(_tomar_pendientes)
            if not eventos:
                try:
                    await asyncio.wait_for(
                        stop.wait(), timeout=configuracion.intervalo_publicador_segundos
                    )
                except asyncio.TimeoutError:
                    pass
                continue
            for evento in eventos:
                mensaje = Message(
                    json.dumps(evento.payload).encode(),
                    content_type="application/json",
                    delivery_mode=DeliveryMode.PERSISTENT,
                    message_id=str(evento.id_evento),
                    type=evento.tipo,
                )
                await exchange.publish(mensaje, routing_key=evento.tipo)
                await asyncio.to_thread(_marcar_publicado, evento.id_evento)
    finally:
        await connection.close()


def _tomar_pendientes() -> list[EventoSaliente]:
    fabrica = obtener_fabrica_sesiones()
    with fabrica() as sesion:
        consulta = (
            select(EventoSaliente)
            .where(
                EventoSaliente.publicado_en.is_(None),
                EventoSaliente.tipo.in_(TIPOS_EVENTO),
            )
            .order_by(EventoSaliente.creado_en)
            .limit(50)
            .with_for_update(skip_locked=True)
        )
        # La consulta se ejecuta dentro de una transacción; se libera el lock
        # después de copiar los eventos y RabbitMQ confirma antes de marcarlos.
        return list(sesion.scalars(consulta))


def _marcar_publicado(id_evento) -> None:
    fabrica = obtener_fabrica_sesiones()
    with fabrica() as sesion:
        sesion.execute(
            update(EventoSaliente)
            .where(
                EventoSaliente.id_evento == id_evento,
                EventoSaliente.publicado_en.is_(None),
            )
            .values(publicado_en=datetime.datetime.now(datetime.UTC))
        )
        sesion.commit()
