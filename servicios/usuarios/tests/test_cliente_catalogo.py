"""Cliente HTTP de catálogo: traducción del contrato de docs/05-comunicacion.md."""

import json

import httpx
import pytest

from app.clientes.catalogo import (
    CatalogoNoDisponible,
    ClienteCatalogoHttp,
    EmailConOtrosDatos,
    EspecialidadInexistente,
    MatriculaYaRegistrada,
)


def cliente_con(respuesta_o_error) -> tuple[ClienteCatalogoHttp, list[httpx.Request]]:
    pedidos: list[httpx.Request] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        if isinstance(respuesta_o_error, Exception):
            raise respuesta_o_error
        return respuesta_o_error

    transporte = httpx.MockTransport(responder)
    return ClienteCatalogoHttp("http://catalogo:8002", 3.0, transporte), pedidos


@pytest.mark.parametrize("codigo_http", [200, 201])
def test_crear_exitoso_o_idempotente(codigo_http):
    cliente, pedidos = cliente_con(httpx.Response(codigo_http, json={}))

    cliente.crear_profesional("dr.gomez@ejemplo.com", "MP-12345", 1)

    assert pedidos[0].method == "POST"
    assert pedidos[0].url == "http://catalogo:8002/interno/profesionales"
    assert json.loads(pedidos[0].content) == {
        "email": "dr.gomez@ejemplo.com",
        "matricula": "MP-12345",
        "id_especialidad": 1,
    }


@pytest.mark.parametrize(
    ("codigo_http", "codigo", "excepcion"),
    [
        (409, "MATRICULA_DUPLICADA", MatriculaYaRegistrada),
        (409, "EMAIL_CON_OTROS_DATOS", EmailConOtrosDatos),
        (422, "ESPECIALIDAD_INEXISTENTE", EspecialidadInexistente),
    ],
)
def test_crear_errores_del_contrato(codigo_http, codigo, excepcion):
    cliente, _ = cliente_con(
        httpx.Response(codigo_http, json={"detail": "x", "codigo": codigo})
    )

    with pytest.raises(excepcion):
        cliente.crear_profesional("dr.gomez@ejemplo.com", "MP-12345", 1)


@pytest.mark.parametrize(
    ("respuesta_o_error", "puede_haber_creado"),
    [
        (httpx.Response(404, json={"detail": "Not Found"}), False),
        (httpx.Response(422, json={"detail": [{"msg": "validación"}]}), False),
        (httpx.Response(500, text="error"), True),
        (httpx.ConnectError("conexión rechazada"), False),
        (httpx.ConnectTimeout("sin conexión"), False),
        (httpx.ReadTimeout("sin respuesta"), True),
        (httpx.RemoteProtocolError("conexión cortada"), True),
    ],
    ids=["404", "422-sin-codigo", "500", "conexion-rechazada", "timeout-conexion",
         "timeout-lectura", "conexion-cortada"],
)
def test_crear_no_disponible(respuesta_o_error, puede_haber_creado):
    cliente, _ = cliente_con(respuesta_o_error)

    with pytest.raises(CatalogoNoDisponible) as error:
        cliente.crear_profesional("dr.gomez@ejemplo.com", "MP-12345", 1)

    assert error.value.puede_haber_creado is puede_haber_creado


def test_crear_sin_url_configurada():
    with pytest.raises(CatalogoNoDisponible) as error:
        ClienteCatalogoHttp("", 3.0).crear_profesional("a@b.com", "MP-1", 1)

    assert error.value.puede_haber_creado is False


def test_borrar_exitoso_codifica_el_email():
    cliente, pedidos = cliente_con(httpx.Response(204))

    cliente.borrar_profesional("dr.gomez@ejemplo.com")

    assert pedidos[0].method == "DELETE"
    assert pedidos[0].url.raw_path == b"/interno/profesionales/dr.gomez%40ejemplo.com"


def test_borrar_con_error():
    cliente, _ = cliente_con(httpx.Response(500))

    with pytest.raises(CatalogoNoDisponible):
        cliente.borrar_profesional("dr.gomez@ejemplo.com")
