"""Cliente del servicio de usuarios: nombre y apellido de los pacientes (ADR 009).

Contrato: docs/05-comunicacion.md (POST /interno/usuarios/nombres). Es una
consulta: si falla, la agenda sale sin nombres.

El timeout de httpx no cubre la resolución DNS: con el contenedor de usuarios
detenido, resolver `usuarios` tarda unos 8 s. Por eso el pedido corre en un
hilo y se espera como máximo TIMEOUT_USUARIOS_SEGUNDOS en total.
"""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as TiempoAgotado
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import configuracion

_hilos = ThreadPoolExecutor(max_workers=8, thread_name_prefix="cliente-usuarios")


class UsuariosNoDisponible(Exception):
    """Usuarios caído, sin respuesta a tiempo o con una respuesta fuera del contrato."""


@dataclass(frozen=True)
class DatosUsuario:
    nombre: str
    apellido: str


class ClienteUsuarios(Protocol):
    def nombres(self, emails: list[str]) -> dict[str, DatosUsuario]: ...


class ClienteUsuariosHttp:
    def __init__(
        self,
        url_base: str,
        timeout_segundos: float,
        transporte: httpx.BaseTransport | None = None,
    ):
        self._url_base = url_base
        self._timeout = timeout_segundos
        self._transporte = transporte

    def nombres(self, emails: list[str]) -> dict[str, DatosUsuario]:
        """Por email; los que usuarios no conoce no aparecen."""
        pedido = _hilos.submit(self._pedir, emails)
        try:
            respuesta = pedido.result(timeout=self._timeout)
        except TiempoAgotado as error:
            raise UsuariosNoDisponible(f"sin respuesta en {self._timeout} s") from error
        if respuesta.status_code != 200:
            raise UsuariosNoDisponible(f"respuesta fuera del contrato: {respuesta.status_code}")
        try:
            return {
                u["email"]: DatosUsuario(nombre=u["nombre"], apellido=u["apellido"])
                for u in respuesta.json()["usuarios"]
            }
        except (ValueError, KeyError, TypeError) as error:
            raise UsuariosNoDisponible("respuesta 200 fuera del contrato") from error

    def _pedir(self, emails: list[str]) -> httpx.Response:
        try:
            with httpx.Client(
                base_url=self._url_base, timeout=self._timeout, transport=self._transporte
            ) as cliente:
                return cliente.post("/interno/usuarios/nombres", json={"emails": emails})
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            raise UsuariosNoDisponible(str(error)) from error


def obtener_cliente_usuarios() -> ClienteUsuarios:
    """Dependencia de FastAPI; los tests la reemplazan por un usuarios falso."""
    return ClienteUsuariosHttp(configuracion.url_usuarios, configuracion.timeout_usuarios_segundos)
