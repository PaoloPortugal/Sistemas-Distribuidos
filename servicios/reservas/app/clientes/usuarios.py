"""Cliente interno del servicio de usuarios."""

from dataclasses import dataclass
from urllib.parse import quote

import httpx

from app.config import configuracion


class UsuariosNoDisponible(Exception):
    """El servicio de usuarios no respondió con un dato utilizable."""


@dataclass(frozen=True)
class DatosUsuario:
    nombre: str
    apellido: str


def obtener_usuario(email: str) -> DatosUsuario:
    try:
        with httpx.Client(
            base_url=configuracion.url_usuarios,
            timeout=configuracion.timeout_usuarios_segundos,
        ) as cliente:
            respuesta = cliente.get(f"/interno/usuarios/{quote(email, safe='')}")
    except (httpx.HTTPError, httpx.InvalidURL) as error:
        raise UsuariosNoDisponible(str(error)) from error
    if respuesta.status_code != 200:
        raise UsuariosNoDisponible(f"respuesta fuera del contrato: {respuesta.status_code}")
    try:
        datos = respuesta.json()
        return DatosUsuario(nombre=datos["nombre"], apellido=datos["apellido"])
    except (ValueError, KeyError, TypeError) as error:
        raise UsuariosNoDisponible("respuesta inválida del servicio de usuarios") from error
