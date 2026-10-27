"""Endpoints internos: los usa reservas para mostrar el nombre del paciente (ADR 009).

Contrato en docs/05-comunicacion.md. Traefik no publica /interno.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.sesion import obtener_sesion
from app.dominio import usuarios

router = APIRouter(prefix="/interno", tags=["interno"])

SesionBD = Annotated[Session, Depends(obtener_sesion)]

MAXIMO_EMAILS = 1000


class UsuarioInterno(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email: str
    nombre: str
    apellido: str


class ConsultaNombres(BaseModel):
    emails: Annotated[list[str], Field(max_length=MAXIMO_EMAILS)]


class Nombres(BaseModel):
    usuarios: list[UsuarioInterno]


class ErrorInterno(BaseModel):
    detail: str
    codigo: str


@router.post("/usuarios/nombres", response_model=Nombres)
def nombres(consulta: ConsultaNombres, sesion: SesionBD):
    """Nombre y apellido de varios usuarios en una llamada; los que no existen se omiten."""
    return Nombres(usuarios=usuarios.usuarios_por_email(sesion, consulta.emails))


@router.get(
    "/usuarios/{email}",
    response_model=UsuarioInterno,
    responses={404: {"model": ErrorInterno, "description": "USUARIO_INEXISTENTE"}},
)
def datos_usuario(email: str, sesion: SesionBD):
    usuario = usuarios.obtener_usuario(sesion, email)
    if usuario is None:
        return JSONResponse(
            {"detail": "Usuario no encontrado", "codigo": "USUARIO_INEXISTENTE"}, status_code=404
        )
    return usuario
