"""Cliente del servicio de reservas: horarios ocupados y bloqueo al borrar (ADR 003).

Contrato: docs/05-comunicacion.md. Las tres operaciones son idempotentes.

El timeout de httpx no cubre la resolución DNS: con el contenedor de reservas
detenido, resolver `reservas` tarda unos 8 s. Por eso cada pedido corre en
un hilo y se espera como máximo TIMEOUT_RESERVAS_SEGUNDOS en total.
"""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as TiempoAgotado
from typing import Protocol

import httpx

from app.config import configuracion

_hilos = ThreadPoolExecutor(max_workers=8, thread_name_prefix="cliente-reservas")


class ErrorReservas(Exception):
    pass


class DisponibilidadConTurno(ErrorReservas):
    pass


class ReservasNoDisponible(ErrorReservas):
    """Reservas caído, sin respuesta a tiempo o con una respuesta fuera del contrato."""


class ClienteReservas(Protocol):
    def ocupadas(self, ids: list[int]) -> set[int]: ...

    def bloquear(self, id_disponibilidad: int) -> None: ...

    def desbloquear(self, id_disponibilidad: int) -> None: ...


class ClienteReservasHttp:
    def __init__(
        self,
        url_base: str,
        timeout_segundos: float,
        transporte: httpx.BaseTransport | None = None,
    ):
        self._url_base = url_base
        self._timeout = timeout_segundos
        self._transporte = transporte

    def ocupadas(self, ids: list[int]) -> set[int]:
        respuesta = self._pedir("POST", "/interno/disponibilidades-ocupadas", json={"ids": ids})
        if respuesta.status_code == 200:
            try:
                return {int(i) for i in respuesta.json()["ocupadas"]}
            except (ValueError, KeyError, TypeError) as error:
                raise ReservasNoDisponible("respuesta 200 fuera del contrato") from error
        raise ReservasNoDisponible(f"respuesta fuera del contrato: {respuesta.status_code}")

    def bloquear(self, id_disponibilidad: int) -> None:
        respuesta = self._pedir("PUT", f"/interno/bloqueos/{id_disponibilidad}")
        if respuesta.status_code == 204:
            return
        if respuesta.status_code == 409 and _codigo_error(respuesta) == "DISPONIBILIDAD_CON_TURNO":
            raise DisponibilidadConTurno
        raise ReservasNoDisponible(f"respuesta fuera del contrato: {respuesta.status_code}")

    def desbloquear(self, id_disponibilidad: int) -> None:
        respuesta = self._pedir("DELETE", f"/interno/bloqueos/{id_disponibilidad}")
        if respuesta.status_code != 204:
            raise ReservasNoDisponible(f"respuesta fuera del contrato: {respuesta.status_code}")

    def _pedir(self, metodo: str, ruta: str, **kwargs) -> httpx.Response:
        pedido = _hilos.submit(self._pedir_sin_limite, metodo, ruta, **kwargs)
        try:
            return pedido.result(timeout=self._timeout)
        except TiempoAgotado as error:
            raise ReservasNoDisponible(f"sin respuesta en {self._timeout} s") from error

    def _pedir_sin_limite(self, metodo: str, ruta: str, **kwargs) -> httpx.Response:
        try:
            with httpx.Client(
                base_url=self._url_base, timeout=self._timeout, transport=self._transporte
            ) as cliente:
                return cliente.request(metodo, ruta, **kwargs)
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            raise ReservasNoDisponible(str(error)) from error


def _codigo_error(respuesta: httpx.Response) -> str | None:
    try:
        return respuesta.json().get("codigo")
    except (ValueError, AttributeError):
        return None


def obtener_cliente_reservas() -> ClienteReservas:
    """Dependencia de FastAPI; los tests la reemplazan por un reservas falso."""
    return ClienteReservasHttp(configuracion.url_reservas, configuracion.timeout_reservas_segundos)
