"""Validación de los JWT que emite el servicio de usuarios (RS256).

Reservas solo tiene la clave pública: puede validar tokens, no emitirlos.
"""

from functools import cache
from pathlib import Path

import jwt

from app.config import configuracion

ALGORITMO = "RS256"
EMISOR = "usuarios"
CLAIMS_OBLIGATORIOS = ["sub", "tipo", "iss", "iat", "exp"]


class TokenInvalido(Exception):
    """El token no se pudo validar: mal formado, vencido o con firma ajena."""


@cache
def _clave_publica() -> str:
    return Path(configuracion.ruta_clave_publica_jwt).read_text()


def olvidar_claves() -> None:
    """Descarta la clave leída, para volver a cargarla desde disco."""
    _clave_publica.cache_clear()


def validar_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            _clave_publica(),
            algorithms=[ALGORITMO],
            issuer=EMISOR,
            options={"require": CLAIMS_OBLIGATORIOS},
        )
    except jwt.InvalidTokenError as error:
        raise TokenInvalido from error
