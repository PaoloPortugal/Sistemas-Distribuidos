"""Cliente HTTP de catálogo: traducción del contrato de docs/05-comunicacion.md."""

import datetime

import httpx
import pytest

from app.clientes.catalogo import (
    CatalogoNoDisponible,
    ClienteCatalogoHttp,
    DatosReserva,
    DisponibilidadInexistente,
    ServicioInexistente,
)

RESPUESTA_OK = {
    "id_disponibilidad": 7,
    "email_profesional": "dr.gomez@ejemplo.com",
    "fecha": "2026-11-05",
    "horario_inicio": "09:00:00",
    "horario_fin": "09:30:00",
    "id_especialidad": 1,
    "servicio": {"id_servicio": 3, "nombre": "Control del niño sano", "id_especialidad": 2},
}


def cliente_con(respuesta_o_error) -> tuple[ClienteCatalogoHttp, list[httpx.Request]]:
    pedidos: list[httpx.Request] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        if isinstance(respuesta_o_error, Exception):
            raise respuesta_o_error
        return respuesta_o_error

    return ClienteCatalogoHttp("http://catalogo:8002", 3.0, httpx.MockTransport(responder)), pedidos


def test_datos_para_reservar():
    cliente, pedidos = cliente_con(httpx.Response(200, json=RESPUESTA_OK))

    datos = cliente.datos_para_reservar(7, 3)

    assert str(pedidos[0].url) == "http://catalogo:8002/interno/disponibilidades/7?id_servicio=3"
    assert datos == DatosReserva(
        id_disponibilidad=7,
        email_profesional="dr.gomez@ejemplo.com",
        fecha=datetime.date(2026, 11, 5),
        horario_inicio=datetime.time(9, 0),
        horario_fin=datetime.time(9, 30),
        id_especialidad=1,
        id_servicio=3,
        id_especialidad_servicio=2,
    )


@pytest.mark.parametrize(
    ("codigo", "excepcion"),
    [("DISPONIBILIDAD_INEXISTENTE", DisponibilidadInexistente), ("SERVICIO_INEXISTENTE", ServicioInexistente)],
)
def test_errores_del_contrato(codigo, excepcion):
    cliente, _ = cliente_con(httpx.Response(404, json={"detail": "x", "codigo": codigo}))

    with pytest.raises(excepcion):
        cliente.datos_para_reservar(7, 3)


@pytest.mark.parametrize(
    "respuesta_o_error",
    [
        httpx.Response(404, json={"detail": "Not Found"}),
        httpx.Response(500, text="error"),
        httpx.Response(200, json={"inesperado": True}),
        httpx.ConnectError("conexión rechazada"),
        httpx.ReadTimeout("sin respuesta"),
    ],
    ids=["404-sin-codigo", "500", "200-fuera-de-contrato", "conexion-rechazada", "timeout"],
)
def test_catalogo_no_disponible(respuesta_o_error):
    cliente, _ = cliente_con(respuesta_o_error)

    with pytest.raises(CatalogoNoDisponible):
        cliente.datos_para_reservar(7, 3)


def test_sin_url_configurada():
    with pytest.raises(CatalogoNoDisponible):
        ClienteCatalogoHttp("", 3.0).datos_para_reservar(7, 3)
