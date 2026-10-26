"""Proceso publicador del outbox: `python -m app.publicador` (ADR 005).

Corre aparte de la API (servicio `reservas-publicador` en Docker Compose),
con la misma imagen. No corre migraciones: si RabbitMQ, la base o las tablas
todavía no están, reintenta con espera creciente.
"""

import asyncio
import datetime
import logging

import aio_pika

from app.config import configuracion
from app.db.sesion import obtener_fabrica_sesiones
from app.dominio.publicacion import publicar_pendientes
from app.eventos import PublicadorRabbit, declarar_exchange

registro = logging.getLogger("app.publicador")


def _ahora() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


async def correr() -> None:
    espera = 1.0
    while True:
        try:
            conexion = await aio_pika.connect(configuracion.url_rabbitmq)
            async with conexion:
                canal = await conexion.channel(publisher_confirms=True, on_return_raises=True)
                publicador = PublicadorRabbit(await declarar_exchange(canal))
                registro.info("Conectado a RabbitMQ; publicando el outbox")
                espera = 1.0
                while True:
                    publicados = await publicar_pendientes(
                        obtener_fabrica_sesiones(),
                        publicador,
                        lote=configuracion.publicador_lote,
                        ahora=_ahora,
                        pausa=configuracion.publicador_pausa_entre_eventos_segundos,
                    )
                    if publicados:
                        registro.info("Publicados %d eventos", publicados)
                    else:
                        await asyncio.sleep(configuracion.publicador_intervalo_segundos)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # RabbitMQ o la base no disponibles, o publicación rechazada
            registro.warning("No se pudo publicar (%s); reintento en %.0f s", error, espera)
            await asyncio.sleep(espera)
            espera = min(espera * 2, configuracion.publicador_espera_maxima_segundos)


def main() -> None:
    logging.basicConfig(
        level=configuracion.nivel_log, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(correr())


if __name__ == "__main__":
    main()
