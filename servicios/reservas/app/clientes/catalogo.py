"""Cliente del servicio catalogo_medicos para validar una reserva.

Contrato: docs/05-comunicacion.md (GET /interno/disponibilidades/{id}).
Es una consulta: si falla, no hay nada que compensar.
"""

import datetime
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import configuracion


class ErrorCatalogo(Exception):
    pass


class DisponibilidadInexistente(ErrorCatalogo):
    pass


class ServicioInexistente(ErrorCatalogo):
    pass


class CatalogoNoDisponible(ErrorCatalogo):
    """Catálogo caído, sin respuesta a tiempo o con una respuesta fuera del contrato."""


@dataclass(frozen=True)
class DatosReserva:
    id_disponibilidad: int
    email_profesional: str
    fecha: datetime.date
    horario_inicio: datetime.time
    horario_fin: datetime.time
    id_especialidad: int
    id_servicio: int
    id_especialidad_servicio: int


class ClienteCatalogo(Protocol):
    def datos_para_reservar(self, id_disponibilidad: int, id_servicio: int) -> DatosReserva: ...


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

    def datos_para_reservar(self, id_disponibilidad: int, id_servicio: int) -> DatosReserva:
        try:
            with httpx.Client(
                base_url=self._url_base, timeout=self._timeout, transport=self._transporte
            ) as cliente:
                respuesta = cliente.get(
                    f"/interno/disponibilidades/{id_disponibilidad}",
                    params={"id_servicio": id_servicio},
                )
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            raise CatalogoNoDisponible(str(error)) from error

        if respuesta.status_code == 200:
            try:
                return _leer(respuesta.json())
            except (ValueError, KeyError, TypeError) as error:
                raise CatalogoNoDisponible("respuesta 200 fuera del contrato") from error
        codigo = _codigo_error(respuesta)
        if respuesta.status_code == 404 and codigo == "DISPONIBILIDAD_INEXISTENTE":
            raise DisponibilidadInexistente
        if respuesta.status_code == 404 and codigo == "SERVICIO_INEXISTENTE":
            raise ServicioInexistente
        raise CatalogoNoDisponible(f"respuesta fuera del contrato: {respuesta.status_code}")


def _leer(datos: dict) -> DatosReserva:
    return DatosReserva(
        id_disponibilidad=int(datos["id_disponibilidad"]),
        email_profesional=datos["email_profesional"],
        fecha=datetime.date.fromisoformat(datos["fecha"]),
        horario_inicio=datetime.time.fromisoformat(datos["horario_inicio"]),
        horario_fin=datetime.time.fromisoformat(datos["horario_fin"]),
        id_especialidad=int(datos["id_especialidad"]),
        id_servicio=int(datos["servicio"]["id_servicio"]),
        id_especialidad_servicio=int(datos["servicio"]["id_especialidad"]),
    )


def _codigo_error(respuesta: httpx.Response) -> str | None:
    try:
        return respuesta.json().get("codigo")
    except (ValueError, AttributeError):
        return None


def obtener_cliente_catalogo() -> ClienteCatalogo:
    """Dependencia de FastAPI; los tests la reemplazan por un catálogo falso."""
    return ClienteCatalogoHttp(configuracion.url_catalogo, configuracion.timeout_catalogo_segundos)
