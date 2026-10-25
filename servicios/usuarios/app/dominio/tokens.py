"""Emisión y validación de JWT firmados con RS256.

usuarios firma con la clave privada; los demás servicios validan con la
clave pública.
"""

from datetime import UTC, datetime, timedelta
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
def _clave_privada() -> str:
    return Path(configuracion.ruta_clave_privada_jwt).read_text()


@cache
def _clave_publica() -> str:
    return Path(configuracion.ruta_clave_publica_jwt).read_text()


def olvidar_claves() -> None:
    """Descarta las claves leídas, para volver a cargarlas desde disco."""
    _clave_privada.cache_clear()
    _clave_publica.cache_clear()


def emitir_token(email: str, tipo: str, ahora: datetime | None = None) -> str:
    ahora = ahora or datetime.now(UTC)
    claims = {
        "sub": email,
        "tipo": tipo,
        "iss": EMISOR,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=configuracion.duracion_token_minutos),
    }
    return jwt.encode(claims, _clave_privada(), algorithm=ALGORITMO)


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
