"""Autenticación con el JWT que emite usuarios.

Reservas no consulta a usuarios: el token firmado alcanza para saber quién es
y de qué tipo. 401 si no hay token válido; 403 si es válido pero no alcanza.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.dominio import tokens

PACIENTE = "PACIENTE"
PROFESIONAL = "PROFESIONAL"

# auto_error=False: sin token se responde 401 con el mismo formato que el resto.
esquema_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class UsuarioToken:
    email: str
    tipo: str


def usuario_autenticado(
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(esquema_bearer)],
) -> UsuarioToken:
    if credenciales is None:
        raise _no_autenticado()
    try:
        claims = tokens.validar_token(credenciales.credentials)
    except tokens.TokenInvalido:
        raise _no_autenticado() from None
    return UsuarioToken(email=claims["sub"], tipo=claims["tipo"])


def profesional_autenticado(
    usuario: Annotated[UsuarioToken, Depends(usuario_autenticado)],
) -> UsuarioToken:
    if usuario.tipo != PROFESIONAL:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo para profesionales")
    return usuario


def paciente_autenticado(
    usuario: Annotated[UsuarioToken, Depends(usuario_autenticado)],
) -> UsuarioToken:
    if usuario.tipo != PACIENTE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo para pacientes")
    return usuario


def _no_autenticado() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "No autenticado",
        headers={"WWW-Authenticate": "Bearer"},
    )


UsuarioActual = Annotated[UsuarioToken, Depends(usuario_autenticado)]
ProfesionalActual = Annotated[UsuarioToken, Depends(profesional_autenticado)]
PacienteActual = Annotated[UsuarioToken, Depends(paciente_autenticado)]

RESPUESTAS_AUTENTICACION = {
    401: {"description": "Token ausente, inválido o vencido"},
}
RESPUESTAS_PROFESIONAL = RESPUESTAS_AUTENTICACION | {
    403: {"description": "El token no es de un profesional"},
}
RESPUESTAS_PACIENTE = RESPUESTAS_AUTENTICACION | {
    403: {"description": "El token no es de un paciente"},
}
