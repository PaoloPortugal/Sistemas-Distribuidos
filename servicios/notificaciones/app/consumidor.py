"""Consumidor de RabbitMQ: escucha el exchange `turnos` (ADR 008).

Topología (la declara este servicio; las declaraciones son idempotentes):
- exchange `turnos` (topic, durable), el mismo que usa el publicador;
- cola `notificaciones.turnos` (quorum, durable), ligada a `turno.confirmado`
  y `turno.cancelado`, con dead-letter a `turnos.dlx` y `x-delivery-limit`;
- exchange `turnos.dlx` (fanout) y cola `notificaciones.turnos.dlq`.

Cada mensaje:
- inválido → reject sin reencolar → va a la DLQ;
- válido → se registra (commit) y **recién después** se hace ack;
- si la base no responde → se espera a que vuelva y se reencola (nack). Cada
  reencolado cuenta para `x-delivery-limit`: un mensaje que falla siempre
  termina en la DLQ en lugar de reintentarse para siempre.

Mientras se procesa un mensaje, el correlation_id del contexto es el que trae
el evento (o, si el cuerpo no se puede leer, la propiedad correlation_id del
mensaje AMQP), así los logs se pueden asociar con la reserva que lo originó.
"""

import asyncio
import datetime
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import configuracion
from app.db.sesion import obtener_fabrica_sesiones
from app.dominio.eventos import (
    TURNO_CANCELADO,
    TURNO_CONFIRMADO,
    EventoInvalido,
    EventoTurno,
    interpretar,
)
from app.dominio.notificaciones import registrar_evento
from app.observabilidad import con_correlation_id

EXCHANGE = "turnos"
EXCHANGE_DLX = "turnos.dlx"
COLA = "notificaciones.turnos"
COLA_DLQ = "notificaciones.turnos.dlq"
ROUTING_KEYS = (TURNO_CONFIRMADO, TURNO_CANCELADO)

registro = logging.getLogger("app.consumidor")


@dataclass
class EstadoProcesos:
    """Lo que informa /salud."""

    consumidor_conectado: bool = False
    ultimo_envio: datetime.datetime | None = None
    errores: list[str] = field(default_factory=list)


def _ahora() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


async def procesar(
    mensaje: AbstractIncomingMessage,
    fabrica_sesiones: Callable[[], Session],
    esperar_base: Callable[[], "asyncio.Future"] | None = None,
) -> str:
    """Procesa un mensaje y devuelve qué se hizo: 'nuevo', 'duplicado', 'invalido' o 'reencolado'."""
    try:
        evento = interpretar(mensaje.body)
    except EventoInvalido as error:
        with con_correlation_id(mensaje.correlation_id):
            registro.error("Mensaje inválido %s, va a la DLQ: %s", mensaje.message_id, error)
        await mensaje.reject(requeue=False)
        return "invalido"

    with con_correlation_id(evento.correlation_id or mensaje.correlation_id):
        return await _procesar_evento(evento, mensaje, fabrica_sesiones, esperar_base)


async def _procesar_evento(
    evento: EventoTurno,
    mensaje: AbstractIncomingMessage,
    fabrica_sesiones: Callable[[], Session],
    esperar_base: Callable[[], "asyncio.Future"] | None,
) -> str:
    def registrar() -> bool:
        with fabrica_sesiones() as sesion:
            return registrar_evento(sesion, evento, _ahora())

    try:
        nuevo = await asyncio.to_thread(registrar)  # commit adentro
    except Exception as error:
        registro.warning("No se pudo registrar %s (%s); se reencola", evento.id_evento, error)
        if esperar_base is not None:
            await esperar_base()
        await mensaje.nack(requeue=True)
        return "reencolado"

    await mensaje.ack()  # recién después del commit
    resultado = "nuevo" if nuevo else "duplicado"
    # Lleva el correlation_id de la reserva y el id_turno: el log de cada mail
    # enviado lleva el mismo id_turno (ADR 010).
    registro.info(
        "Evento %s %s del turno %d: %s",
        evento.tipo,
        evento.id_evento,
        evento.id_turno,
        resultado,
        extra={
            "id_evento": str(evento.id_evento),
            "tipo_evento": evento.tipo,
            "id_turno": evento.id_turno,
            "resultado": resultado,
        },
    )
    return resultado


async def declarar_topologia(canal: aio_pika.abc.AbstractChannel) -> aio_pika.abc.AbstractQueue:
    exchange = await canal.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
    dlx = await canal.declare_exchange(EXCHANGE_DLX, aio_pika.ExchangeType.FANOUT, durable=True)
    dlq = await canal.declare_queue(COLA_DLQ, durable=True)
    await dlq.bind(dlx)
    cola = await canal.declare_queue(
        COLA,
        durable=True,
        arguments={
            "x-queue-type": "quorum",
            "x-dead-letter-exchange": EXCHANGE_DLX,
            "x-delivery-limit": configuracion.limite_entregas,
        },
    )
    for routing_key in ROUTING_KEYS:
        await cola.bind(exchange, routing_key=routing_key)
    return cola


async def _esperar_base() -> None:
    """Espera, con espera creciente, a que la base vuelva a responder."""
    espera = 1.0
    while True:
        try:
            def probar():
                with obtener_fabrica_sesiones()() as sesion:
                    sesion.execute(text("SELECT 1"))

            await asyncio.to_thread(probar)
            return
        except Exception:
            await asyncio.sleep(espera)
            espera = min(espera * 2, 30.0)


async def consumir(estado: EstadoProcesos) -> None:
    """Bucle del consumidor: si se pierde la conexión, se reconecta con espera creciente."""
    espera = 1.0
    while True:
        try:
            conexion = await aio_pika.connect(configuracion.url_rabbitmq)
            async with conexion:
                canal = await conexion.channel()
                await canal.set_qos(prefetch_count=configuracion.prefetch)
                cola = await declarar_topologia(canal)
                estado.consumidor_conectado = True
                registro.info("Consumiendo %s", COLA)
                espera = 1.0
                async with cola.iterator() as mensajes:
                    async for mensaje in mensajes:
                        await procesar(mensaje, obtener_fabrica_sesiones(), _esperar_base)
        except asyncio.CancelledError:
            estado.consumidor_conectado = False
            raise
        except Exception as error:
            estado.consumidor_conectado = False
            registro.warning("Consumidor desconectado (%s); reintento en %.0f s", error, espera)
            await asyncio.sleep(espera)
            espera = min(espera * 2, 30.0)
        else:
            estado.consumidor_conectado = False
