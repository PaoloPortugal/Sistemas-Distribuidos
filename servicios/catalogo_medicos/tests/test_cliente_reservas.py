"""Cliente HTTP de reservas: traducción del contrato de docs/05-comunicacion.md."""

import json
import time

import httpx
import pytest

from app.clientes.reservas import ClienteReservasHttp, DisponibilidadConTurno, ReservasNoDisponible


def cliente_con(respuesta_o_error) -> tuple[ClienteReservasHttp, list[httpx.Request]]:
    pedidos: list[httpx.Request] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        if isinstance(respuesta_o_error, Exception):
            raise respuesta_o_error
        return respuesta_o_error

    return ClienteReservasHttp("http://reservas:8003", 2.0, httpx.MockTransport(responder)), pedidos


def test_ocupadas():
    cliente, pedidos = cliente_con(httpx.Response(200, json={"ocupadas": [8]}))

    assert cliente.ocupadas([7, 8, 9]) == {8}
    assert pedidos[0].method == "POST"
    assert str(pedidos[0].url) == "http://reservas:8003/interno/disponibilidades-ocupadas"
    assert json.loads(pedidos[0].content) == {"ids": [7, 8, 9]}


def test_bloquear():
    cliente, pedidos = cliente_con(httpx.Response(204))

    cliente.bloquear(7)

    assert (pedidos[0].method, str(pedidos[0].url)) == (
        "PUT",
        "http://reservas:8003/interno/bloqueos/7",
    )


def test_bloquear_con_turno():
    cliente, _ = cliente_con(
        httpx.Response(409, json={"detail": "x", "codigo": "DISPONIBILIDAD_CON_TURNO"})
    )

    with pytest.raises(DisponibilidadConTurno):
        cliente.bloquear(7)


def test_desbloquear():
    cliente, pedidos = cliente_con(httpx.Response(204))

    cliente.desbloquear(7)

    assert (pedidos[0].method, str(pedidos[0].url)) == (
        "DELETE",
        "http://reservas:8003/interno/bloqueos/7",
    )


FUERA_DE_CONTRATO = [
    httpx.Response(409, json={"detail": "otro"}),
    httpx.Response(500, text="error"),
    httpx.ConnectError("conexión rechazada"),
    httpx.ReadTimeout("sin respuesta"),
]
IDS_FUERA_DE_CONTRATO = ["409-sin-codigo", "500", "conexion-rechazada", "timeout"]


@pytest.mark.parametrize("respuesta_o_error", FUERA_DE_CONTRATO, ids=IDS_FUERA_DE_CONTRATO)
@pytest.mark.parametrize("operacion", ["ocupadas", "bloquear", "desbloquear"])
def test_reservas_no_disponible(respuesta_o_error, operacion):
    cliente, _ = cliente_con(respuesta_o_error)
    argumento = [7] if operacion == "ocupadas" else 7

    with pytest.raises(ReservasNoDisponible):
        getattr(cliente, operacion)(argumento)


def test_ocupadas_200_fuera_de_contrato():
    cliente, _ = cliente_con(httpx.Response(200, json={"inesperado": True}))

    with pytest.raises(ReservasNoDisponible):
        cliente.ocupadas([7])


def test_el_timeout_cubre_todo_el_pedido():
    """Aunque la demora no sea de httpx (por ejemplo, el DNS), se corta a tiempo."""

    def lento(_pedido: httpx.Request) -> httpx.Response:
        time.sleep(1.0)
        return httpx.Response(200, json={"ocupadas": []})

    cliente = ClienteReservasHttp("http://reservas:8003", 0.2, httpx.MockTransport(lento))

    inicio = time.monotonic()
    with pytest.raises(ReservasNoDisponible):
        cliente.ocupadas([7])
    assert time.monotonic() - inicio < 0.6


def test_sin_url_configurada():
    with pytest.raises(ReservasNoDisponible):
        ClienteReservasHttp("", 2.0).ocupadas([7])
