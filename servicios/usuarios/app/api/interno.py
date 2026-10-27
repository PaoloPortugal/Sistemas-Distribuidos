"""Endpoints internos para otros servicios del sistema."""

from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.esquemas import Error
from app.db.modelos import Usuario
from app.db.sesion import obtener_sesion

router = APIRouter(prefix="/interno", tags=["interno"])


@router.get(
    "/usuarios/{email}",
    response_model=dict[str, str],
    responses={404: {"model": Error, "description": "Usuario no encontrado"}},
)
def datos_usuario(
    email: str,
    sesion: Session = Depends(obtener_sesion),
):
    usuario = sesion.get(Usuario, unquote(email).lower())
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    return {"email": usuario.email, "nombre": usuario.nombre, "apellido": usuario.apellido}
