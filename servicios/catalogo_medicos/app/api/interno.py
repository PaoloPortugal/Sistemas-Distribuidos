"""Endpoints internos: los usan los servicios de usuarios y reservas, no el cliente web.

Contrato en docs/05-comunicacion.md. Traefik no publica /interno.
"""

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints
from sqlalchemy.orm import Session

from app.db.sesion import obtener_sesion
from app.dominio import catalogo, profesionales

router = APIRouter(prefix="/interno", tags=["interno"])

SesionBD = Annotated[Session, Depends(obtener_sesion)]

Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class DatosProfesional(BaseModel):
    email: EmailStr
    matricula: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)
    ]
    id_especialidad: Annotated[int, Field(gt=0)]
    nombre: Nombre
    apellido: Nombre


class ProfesionalCreado(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email: str
    matricula: str
    id_especialidad: int
    nombre: str
    apellido: str


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


class ServicioInterno(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_servicio: int
    nombre: str
    id_especialidad: int


class DisponibilidadParaReservar(BaseModel):
    id_disponibilidad: int
    email_profesional: str
    fecha: datetime.date
    horario_inicio: datetime.time
    horario_fin: datetime.time
    id_especialidad: int
    servicio: ServicioInterno


@router.get(
    "/disponibilidades/{id_disponibilidad}",
    response_model=DisponibilidadParaReservar,
    responses={
        404: {"model": ErrorInterno, "description": "DISPONIBILIDAD_INEXISTENTE o SERVICIO_INEXISTENTE"},
    },
)
def obtener_para_reservar(
    id_disponibilidad: int,
    id_servicio: Annotated[int, Query(description="Servicio que se quiere reservar")],
    sesion: SesionBD,
):
    """Lo que reservas necesita para validar y copiar en el turno (ADR 006)."""
    try:
        disponibilidad, id_especialidad, servicio = catalogo.datos_para_reservar(
            sesion, id_disponibilidad, id_servicio
        )
    except catalogo.DisponibilidadNoEncontrada:
        return _error(404, "DISPONIBILIDAD_INEXISTENTE", "La disponibilidad no existe")
    except catalogo.ServicioNoEncontrado:
        return _error(404, "SERVICIO_INEXISTENTE", "El servicio no existe")
    return DisponibilidadParaReservar(
        id_disponibilidad=disponibilidad.id_disponibilidad,
        email_profesional=disponibilidad.email_profesional,
        fecha=disponibilidad.fecha,
        horario_inicio=disponibilidad.horario_inicio,
        horario_fin=disponibilidad.horario_fin,
        id_especialidad=id_especialidad,
        servicio=ServicioInterno.model_validate(servicio),
    )
