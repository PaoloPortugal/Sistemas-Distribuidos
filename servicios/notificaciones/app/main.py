"""Servicio de notificaciones: un contenedor con dos tareas asyncio (ADR 008).

- consumidor: eventos de RabbitMQ → NOTIFICACION en PENDIENTE;
- envío: NOTIFICACION PENDIENTE → mail por SMTP → ENVIADO o FALLIDO.

/salud responde 503 si el consumidor perdió la conexión con RabbitMQ.
"""

import asyncio
import datetime
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import configuracion
from app.consumidor import EstadoProcesos, consumir
from app.correo import servidor_configurado
from app.db.sesion import obtener_fabrica_sesiones
from app.dominio.envio import PoliticaReintentos, enviar_pendientes

registro = logging.getLogger("app.envio")

estado = EstadoProcesos()


async def enviar_en_bucle() -> None:
    politica = PoliticaReintentos(
        max_intentos=configuracion.max_intentos_envio,
        espera_minima=configuracion.espera_minima_segundos,
        espera_maxima=configuracion.espera_maxima_segundos,
    )
    correo = servidor_configurado()
    while True:
        procesados = 0
        try:
            resultado = await asyncio.to_thread(
                enviar_pendientes,
                obtener_fabrica_sesiones(),
                correo,
                politica,
                ahora=lambda: datetime.datetime.now(datetime.UTC),
            )
            estado.ultimo_envio = datetime.datetime.now(datetime.UTC)
            procesados = resultado.procesados
            if procesados:
                registro.info(
                    "Envío: %d enviados, %d reprogramados, %d fallidos",
                    resultado.enviados, resultado.reprogramados, resultado.fallidos,
                )
        except Exception as error:  # la base no responde: se reintenta en el próximo ciclo
            registro.warning("Envío interrumpido: %s", error)
        if not procesados:
            await asyncio.sleep(configuracion.envio_intervalo_segundos)


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    tareas = []
    if configuracion.iniciar_procesos:
        logging.basicConfig(
            level=configuracion.nivel_log, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
        tareas = [asyncio.create_task(consumir(estado)), asyncio.create_task(enviar_en_bucle())]
    yield
    for tarea in tareas:
        tarea.cancel()


app = FastAPI(title="Servicio de Notificaciones", lifespan=ciclo_de_vida)


@app.get("/salud")
def salud():
    cuerpo = {
        "estado": "ok" if estado.consumidor_conectado else "sin conexión a RabbitMQ",
        "servicio": "notificaciones",
        "consumidor_conectado": estado.consumidor_conectado,
        "ultimo_envio": estado.ultimo_envio,
    }
    return JSONResponse(
        jsonable(cuerpo), status_code=200 if estado.consumidor_conectado else 503
    )


def jsonable(cuerpo: dict) -> dict:
    return {
        clave: valor.isoformat() if isinstance(valor, datetime.datetime) else valor
        for clave, valor in cuerpo.items()
    }
