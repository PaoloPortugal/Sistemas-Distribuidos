"""Cliente del servicio catalogo_medicos para el alta y la baja de profesionales.

Contrato: docs/05-comunicacion.md (POST y DELETE /interno/profesionales).
Ambas operaciones son idempotentes por email, así que reintentar o compensar
es seguro.
"""

from typing import Protocol
from urllib.parse import quote

import httpx

from app.config import configuracion


class ErrorCatalogo(Exception):
    """Catálogo rechazó la operación o no se pudo completar."""


class MatriculaYaRegistrada(ErrorCatalogo):
    pass


class EmailConOtrosDatos(ErrorCatalogo):
    """Catálogo ya tiene un profesional con ese email y otros datos."""


class EspecialidadInexistente(ErrorCatalogo):
    pass


class CatalogoNoDisponible(ErrorCatalogo):
    """Catálogo caído, sin respuesta a tiempo o con una respuesta fuera del contrato.

    `puede_haber_creado` indica si el pedido pudo haberse aplicado igual (por
    ejemplo, un timeout después de enviarlo); en ese caso hay que compensar.
    """

    def __init__(self, motivo: str, *, puede_haber_creado: bool):
        super().__init__(motivo)
        self.puede_haber_creado = puede_haber_creado


class ClienteCatalogo(Protocol):
    def crear_profesional(self, email: str, matricula: str, id_especialidad: int) -> None: ...

    def borrar_profesional(self, email: str) -> None: ...


class ClienteCatalogoHttp:
    def __init__(
        self,
        url_base: str,
        timeout_segundos: float,
        transporte: httpx.BaseTransport | None = None,
    ):
        self._url_base = url_base
        self._timeout = timeout_segundos
        self._transporte = transporte

    def crear_profesional(self, email: str, matricula: str, id_especialidad: int) -> None:
        respuesta = self._enviar(
            "POST",
            "/interno/profesionales",
            json={"email": email, "matricula": matricula, "id_especialidad": id_especialidad},
        )
        if respuesta.status_code in (200, 201):
            return
        codigo = _codigo_error(respuesta)
        if respuesta.status_code == 409 and codigo == "MATRICULA_DUPLICADA":
            raise MatriculaYaRegistrada
        if respuesta.status_code == 409 and codigo == "EMAIL_CON_OTROS_DATOS":
            raise EmailConOtrosDatos
        if respuesta.status_code == 422 and codigo == "ESPECIALIDAD_INEXISTENTE":
            raise EspecialidadInexistente
        raise CatalogoNoDisponible(
            f"respuesta fuera del contrato: {respuesta.status_code}",
            puede_haber_creado=respuesta.status_code >= 500,
        )

    def borrar_profesional(self, email: str) -> None:
        respuesta = self._enviar("DELETE", f"/interno/profesionales/{quote(email, safe='')}")
        if respuesta.status_code != 204:
            raise CatalogoNoDisponible(
                f"respuesta fuera del contrato: {respuesta.status_code}",
                puede_haber_creado=True,
            )

    def _enviar(self, metodo: str, ruta: str, **opciones) -> httpx.Response:
        try:
            with httpx.Client(
                base_url=self._url_base, timeout=self._timeout, transport=self._transporte
            ) as cliente:
                return cliente.request(metodo, ruta, **opciones)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.UnsupportedProtocol) as error:
            # El pedido no llegó a catálogo: no pudo haber creado nada.
            raise CatalogoNoDisponible(str(error), puede_haber_creado=False) from error
        except httpx.HTTPError as error:
            # Timeout de lectura o conexión cortada: el pedido pudo haberse aplicado.
            raise CatalogoNoDisponible(str(error), puede_haber_creado=True) from error


def _codigo_error(respuesta: httpx.Response) -> str | None:
    try:
        return respuesta.json().get("codigo")
    except (ValueError, AttributeError):
        return None


def obtener_cliente_catalogo() -> ClienteCatalogo:
    """Dependencia de FastAPI; los tests la reemplazan por un catálogo falso."""
    return ClienteCatalogoHttp(configuracion.url_catalogo, configuracion.timeout_catalogo_segundos)
