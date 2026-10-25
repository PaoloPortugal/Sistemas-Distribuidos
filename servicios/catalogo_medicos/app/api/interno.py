"""Endpoints internos: los usa el servicio de usuarios, no el cliente web.

Contrato en docs/05-comunicacion.md. Traefik no publica /interno.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints
from sqlalchemy.orm import Session

from app.db.sesion import obtener_sesion
from app.dominio import profesionales

router = APIRouter(prefix="/interno", tags=["interno"])

SesionBD = Annotated[Session, Depends(obtener_sesion)]


class DatosProfesional(BaseModel):
    email: EmailStr
    matricula: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)
    ]
    id_especialidad: Annotated[int, Field(gt=0)]


class ProfesionalCreado(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email: str
    matricula: str
    id_especialidad: int


class ErrorInterno(BaseModel):
    detail: str
    codigo: str


def _error(codigo_http: int, codigo: str, detalle: str) -> JSONResponse:
    return JSONResponse({"detail": detalle, "codigo": codigo}, status_code=codigo_http)


@router.post(
    "/profesionales",
    status_code=status.HTTP_201_CREATED,
    response_model=ProfesionalCreado,
    responses={
        200: {"model": ProfesionalCreado, "description": "Ya existía con los mismos datos"},
        409: {"model": ErrorInterno, "description": "MATRICULA_DUPLICADA o EMAIL_CON_OTROS_DATOS"},
        422: {"model": ErrorInterno, "description": "ESPECIALIDAD_INEXISTENTE"},
    },
)
def crear_profesional(datos: DatosProfesional, sesion: SesionBD, respuesta: Response):
    try:
        profesional, resultado = profesionales.crear_profesional(
            sesion, **datos.model_dump()
        )
    except profesionales.MatriculaDuplicada:
        return _error(409, "MATRICULA_DUPLICADA", "La matrícula ya está registrada")
    except profesionales.EmailConOtrosDatos:
        return _error(
            409, "EMAIL_CON_OTROS_DATOS", "Ya existe un profesional con ese email y otros datos"
        )
    except profesionales.EspecialidadInexistente:
        return _error(422, "ESPECIALIDAD_INEXISTENTE", "La especialidad no existe")
    if resultado is profesionales.ResultadoAlta.YA_EXISTIA:
        respuesta.status_code = status.HTTP_200_OK
    return profesional


@router.delete(
    "/profesionales/{email}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={409: {"model": ErrorInterno, "description": "PROFESIONAL_CON_DISPONIBILIDADES"}},
)
def borrar_profesional(email: str, sesion: SesionBD):
    try:
        profesionales.borrar_profesional(sesion, email)
    except profesionales.ProfesionalConDisponibilidades:
        return _error(
            409,
            "PROFESIONAL_CON_DISPONIBILIDADES",
            "El profesional tiene disponibilidades y no se puede borrar",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
