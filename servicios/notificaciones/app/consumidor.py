"""Consumidor idempotente de eventos de turnos."""

import asyncio
import datetime
import json
import logging
import uuid

import aio_pika
from aio_pika import ExchangeType, IncomingMessage
from sqlalchemy.exc import IntegrityError

from app.config import configuracion
from app.correo import enviar_notificacion
from app.db.modelos import EventoProcesado
from app.db.sesion import obtener_fabrica_sesiones

logger = logging.getLogger(__name__)
EXCHANGE = "turnos"
QUEUE = "notificaciones"


async def ejecutar_consumidor(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await _consumir(stop)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("fallo_consumidor_notificaciones")
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass


async def _consumir(stop: asyncio.Event) -> None:
    connection = await aio_pika.connect_robust(configuracion.url_rabbitmq)
    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)
        exchange = await channel.declare_exchange(EXCHANGE, ExchangeType.TOPIC, durable=True)
        queue = await channel.declare_queue(QUEUE, durable=True)
        await queue.bind(exchange, routing_key="turno.*")
        async with queue.iterator() as mensajes:
            async for mensaje in mensajes:
                if stop.is_set():
                    break
                await _procesar_con_reintentos(mensaje)
    finally:
        await connection.close()


async def _procesar_con_reintentos(mensaje: IncomingMessage) -> None:
    intentos = int((mensaje.headers or {}).get("x-intentos", 0))
    try:
        payload = json.loads(mensaje.body)
        await _procesar(payload)
    except Exception:
        logger.exception("fallo_procesando_evento", extra={"event_id": mensaje.message_id})
        if intentos >= configuracion.max_reintentos:
            await mensaje.reject(requeue=False)
            return
        await asyncio.sleep(min(2**intentos, 30))
        await mensaje.channel.default_exchange.publish(
            aio_pika.Message(
                mensaje.body,
                content_type=mensaje.content_type,
                message_id=mensaje.message_id,
                type=mensaje.type,
                headers={"x-intentos": intentos + 1},
                delivery_mode=mensaje.delivery_mode,
            ),
            routing_key=mensaje.routing_key,
        )
        await mensaje.ack()
    else:
        await mensaje.ack()


async def _procesar(payload: dict) -> None:
    id_evento = uuid.UUID(payload["id_evento"])
    if _ya_procesado(id_evento):
        return
    tipo = payload["tipo"]
    asunto = "Turno confirmado" if tipo == "turno.confirmado" else "Turno cancelado"
    cuerpo = _cuerpo(tipo, payload)
    await enviar_notificacion(
        destinatario=payload["email_paciente"], asunto=asunto, cuerpo=cuerpo
    )
    await enviar_notificacion(
        destinatario=payload["email_profesional"], asunto=asunto, cuerpo=cuerpo
    )
    _registrar_procesado(id_evento, tipo)


def _ya_procesado(id_evento: uuid.UUID) -> bool:
    with obtener_fabrica_sesiones()() as sesion:
        return sesion.get(EventoProcesado, id_evento) is not None


def _registrar_procesado(id_evento: uuid.UUID, tipo: str) -> None:
    with obtener_fabrica_sesiones()() as sesion:
        try:
            sesion.add(
                EventoProcesado(
                    id_evento=id_evento,
                    tipo=tipo,
                    procesado_en=datetime.datetime.now(datetime.UTC),
                )
            )
            sesion.commit()
        except IntegrityError:
            sesion.rollback()


def _cuerpo(tipo: str, payload: dict) -> str:
    accion = "confirmado" if tipo == "turno.confirmado" else "cancelado"
    cuerpo = (
        f"Su turno fue {accion}.\n\n"
        f"Fecha: {payload['fecha']}\n"
        f"Horario: {payload['horario_inicio']} - {payload['horario_fin']}\n"
    )
    if tipo == "turno.cancelado":
        cuerpo += (
            f"Cancelado por: {payload.get('cancelado_por', 'desconocido')}\n"
            f"Motivo: {payload.get('motivo') or 'Sin motivo indicado'}\n"
        )
    return cuerpo
