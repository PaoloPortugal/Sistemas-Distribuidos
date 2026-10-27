"""Publicación de eventos turno.confirmado / turno.cancelado en RabbitMQ.

No existe turno.modificado: modificar un turno es cancelarlo y reservar otro.

Exchange `turnos` (topic, durable); routing key = tipo del evento;
message_id = id_evento; mensajes persistentes. El canal usa publisher
confirms: `publicar` vuelve solo cuando el broker confirmó, y lanza una
excepción si lo rechazó (Nack) o si el mensaje no llegó a ninguna cola.
"""

import json

import aio_pika
from aio_pika.abc import AbstractExchange

from app.db.modelos import EventoSaliente

EXCHANGE = "turnos"


async def declarar_exchange(canal: aio_pika.abc.AbstractChannel) -> AbstractExchange:
    return await canal.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)


class PublicadorRabbit:
    def __init__(self, exchange: AbstractExchange):
        self._exchange = exchange

    async def publicar(self, evento: EventoSaliente) -> None:
        mensaje = aio_pika.Message(
            body=json.dumps(evento.payload, ensure_ascii=False).encode("utf-8"),
            message_id=str(evento.id_evento),
            type=evento.tipo,
            content_type="application/json",
            content_encoding="utf-8",
            timestamp=evento.creado_en,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        # mandatory: si ninguna cola está ligada, el broker lo devuelve y aio-pika
        # lanza PublishError en lugar de descartarlo en silencio.
        await self._exchange.publish(mensaje, routing_key=evento.tipo, mandatory=True)
