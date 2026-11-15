"""Logs JSON y correlation_id (app/observabilidad.py, idéntico en los cuatro servicios)."""

import json
import logging
import sys
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app
from app.observabilidad import (
    ENCABEZADO,
    FormateadorJson,
    MiddlewareCorrelacion,
    con_correlation_id,
    encabezados_correlacion,
    obtener_correlation_id,
)


def _registro(mensaje: str, *argumentos, nivel=logging.INFO, **extra) -> logging.LogRecord:
    registro = logging.LogRecord("app.prueba", nivel, __file__, 1, mensaje, argumentos, None)
    registro.__dict__.update(extra)
    return registro


def test_una_linea_json_con_los_campos_comunes_y_los_extra():
    with con_correlation_id("pedido-123"):
        linea = FormateadorJson("servicio-x").format(_registro("Turno %d reservado", 5, id_turno=5))

    assert "\n" not in linea
    datos = json.loads(linea)
    assert datos["servicio"] == "servicio-x"
    assert datos["nivel"] == "INFO"
    assert datos["logger"] == "app.prueba"
    assert datos["mensaje"] == "Turno 5 reservado"
    assert datos["correlation_id"] == "pedido-123"
    assert datos["id_turno"] == 5
    assert "fecha" in datos


def test_sin_pedido_el_correlation_id_es_null():
    datos = json.loads(FormateadorJson("x").format(_registro("arranque")))
    assert datos["correlation_id"] is None


def test_la_excepcion_va_en_la_linea():
    try:
        raise ValueError("falló")
    except ValueError:
        registro = logging.LogRecord(
            "app.prueba", logging.ERROR, __file__, 1, "error", None, sys.exc_info()
        )
    datos = json.loads(FormateadorJson("x").format(registro))
    assert "ValueError: falló" in datos["excepcion"]


def test_genera_un_correlation_id_si_no_llega():
    respuesta = TestClient(app).get("/salud")
    uuid.UUID(respuesta.headers[ENCABEZADO])  # es un UUID válido


def test_devuelve_el_correlation_id_recibido():
    respuesta = TestClient(app).get("/salud", headers={ENCABEZADO: "abc-123"})
    assert respuesta.headers[ENCABEZADO] == "abc-123"


def test_un_correlation_id_con_formato_invalido_se_reemplaza():
    respuesta = TestClient(app).get("/salud", headers={ENCABEZADO: "a b <script>"})
    uuid.UUID(respuesta.headers[ENCABEZADO])


def _app_que_devuelve_el_correlation_id() -> FastAPI:
    prueba = FastAPI()
    prueba.add_middleware(MiddlewareCorrelacion)

    @prueba.get("/sincronico")
    def sincronico():  # corre en otro hilo: el contexto se copia
        return {"correlation_id": obtener_correlation_id(), "encabezados": encabezados_correlacion()}

    @prueba.get("/asincronico")
    async def asincronico():
        return {"correlation_id": obtener_correlation_id()}

    return prueba


def test_el_endpoint_ve_el_correlation_id_del_pedido():
    cliente = TestClient(_app_que_devuelve_el_correlation_id())
    sincronico = cliente.get("/sincronico", headers={ENCABEZADO: "abc-123"}).json()
    assert sincronico == {"correlation_id": "abc-123", "encabezados": {ENCABEZADO: "abc-123"}}
    asincronico = cliente.get("/asincronico", headers={ENCABEZADO: "xyz"}).json()
    assert asincronico == {"correlation_id": "xyz"}


def test_fuera_de_un_pedido_no_hay_correlation_id():
    TestClient(app).get("/salud", headers={ENCABEZADO: "abc-123"})
    assert obtener_correlation_id() is None
    assert encabezados_correlacion() == {}


def test_registra_cada_pedido_con_metodo_ruta_estado_y_duracion(caplog):
    with caplog.at_level(logging.INFO, logger="app.pedidos"):
        TestClient(app).get("/no-existe", headers={ENCABEZADO: "abc-123"})

    (registro,) = [r for r in caplog.records if r.name == "app.pedidos"]
    assert registro.metodo == "GET"
    assert registro.ruta == "/no-existe"
    assert registro.estado == 404
    assert registro.duracion_ms >= 0
    assert registro.correlation_id == "abc-123"


def test_salud_se_registra_en_debug(caplog):
    with caplog.at_level(logging.INFO, logger="app.pedidos"):
        TestClient(app).get("/salud")
    assert not [r for r in caplog.records if r.name == "app.pedidos"]
