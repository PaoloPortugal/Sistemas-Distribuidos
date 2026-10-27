"""Cliente HTTP de usuarios: traducción del contrato de docs/05-comunicacion.md (ADR 009)."""

import json
import time

import httpx
import pytest

from app.clientes.usuarios import ClienteUsuariosHttp, DatosUsuario, UsuariosNoDisponible


def cliente_con(respuesta_o_error) -> tuple[ClienteUsuariosHttp, list[httpx.Request]]:
    pedidos: list[httpx.Request] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        if isinstance(respuesta_o_error, Exception):
            raise respuesta_o_error
        return respuesta_o_error

    return ClienteUsuariosHttp("http://usuarios:8001", 3.0, httpx.MockTransport(responder)), pedidos


def test_nombres():
    cliente, pedidos = cliente_con(
        httpx.Response(
            200,
            json={"usuarios": [{"email": "ana.perez@ejemplo.com", "nombre": "Ana", "apellido": "Pérez"}]},
        )
    )

    nombres = cliente.nombres(["ana.perez@ejemplo.com", "nadie@ejemplo.com"])

    assert nombres == {"ana.perez@ejemplo.com": DatosUsuario("Ana", "Pérez")}
    assert (pedidos[0].method, str(pedidos[0].url)) == (
        "POST",
        "http://usuarios:8001/interno/usuarios/nombres",
    )
    assert json.loads(pedidos[0].content) == {
        "emails": ["ana.perez@ejemplo.com", "nadie@ejemplo.com"]
    }


@pytest.mark.parametrize(
    "respuesta_o_error",
    [
        httpx.Response(404, json={"detail": "Not Found"}),
        httpx.Response(500, text="error"),
        httpx.Response(200, json={"inesperado": True}),
        httpx.ConnectError("conexión rechazada"),
        httpx.ReadTimeout("sin respuesta"),
    ],
    ids=["404", "500", "200-fuera-de-contrato", "conexion-rechazada", "timeout"],
)
def test_usuarios_no_disponible(respuesta_o_error):
    cliente, _ = cliente_con(respuesta_o_error)

    with pytest.raises(UsuariosNoDisponible):
        cliente.nombres(["ana.perez@ejemplo.com"])


def test_el_timeout_cubre_todo_el_pedido():
    """Aunque la demora no sea de httpx (por ejemplo, el DNS), se corta a tiempo."""

    def lento(_pedido: httpx.Request) -> httpx.Response:
        time.sleep(1.0)
        return httpx.Response(200, json={"usuarios": []})

    cliente = ClienteUsuariosHttp("http://usuarios:8001", 0.2, httpx.MockTransport(lento))

    inicio = time.monotonic()
    with pytest.raises(UsuariosNoDisponible):
        cliente.nombres(["ana.perez@ejemplo.com"])
    assert time.monotonic() - inicio < 0.6


def test_sin_url_configurada():
    with pytest.raises(UsuariosNoDisponible):
        ClienteUsuariosHttp("", 3.0).nombres(["ana.perez@ejemplo.com"])
