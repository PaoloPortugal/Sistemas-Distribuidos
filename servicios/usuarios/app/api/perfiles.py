"""Endpoints de perfiles: datos del usuario autenticado."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.esquemas import Error, UsuarioPublico
from app.db.modelos import Usuario
from app.db.sesion import obtener_sesion
from app.dominio import tokens, usuarios

router = APIRouter(tags=["perfiles"])

# auto_error=False: sin token se responde 401 con el mismo formato que el resto.
esquema_bearer = HTTPBearer(auto_error=False)


def _no_autenticado() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "No autenticado",
        headers={"WWW-Authenticate": "Bearer"},
    )


def obtener_usuario_actual(
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(esquema_bearer)],
    sesion: Annotated[Session, Depends(obtener_sesion)],
) -> Usuario:
    if credenciales is None:
        raise _no_autenticado()
    try:
        claims = tokens.validar_token(credenciales.credentials)
    except tokens.TokenInvalido:
        raise _no_autenticado() from None
    usuario = usuarios.obtener_usuario(sesion, claims["sub"])
    if usuario is None:
        raise _no_autenticado()
    return usuario


@router.get(
    "/yo",
    response_model=UsuarioPublico,
    responses={401: {"model": Error, "description": "Token ausente, inválido o vencido"}},
)
def yo(usuario: Annotated[Usuario, Depends(obtener_usuario_actual)]):
    return usuario
