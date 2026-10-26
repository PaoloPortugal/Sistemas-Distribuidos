"""Endpoints de médicos: especialidades, servicios y profesionales."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.esquemas import EspecialidadPublica, Error, ProfesionalPublico, ServicioPublico
from app.api.seguridad import RESPUESTAS_AUTENTICACION, UsuarioActual
from app.db.sesion import obtener_sesion
from app.dominio import catalogo

router = APIRouter(tags=["médicos"])

SesionBD = Annotated[Session, Depends(obtener_sesion)]

ESPECIALIDAD_NO_ENCONTRADA = "La especialidad no existe"
RESPUESTA_404 = {404: {"model": Error, "description": ESPECIALIDAD_NO_ENCONTRADA}}


@router.get(
    "/especialidades",
    response_model=list[EspecialidadPublica],
    responses=RESPUESTAS_AUTENTICACION,
)
def listar_especialidades(_usuario: UsuarioActual, sesion: SesionBD):
    return catalogo.listar_especialidades(sesion)


@router.get(
    "/especialidades/{id_especialidad}/servicios",
    response_model=list[ServicioPublico],
    responses=RESPUESTAS_AUTENTICACION | RESPUESTA_404,
)
def listar_servicios(id_especialidad: int, _usuario: UsuarioActual, sesion: SesionBD):
    try:
        return catalogo.listar_servicios(sesion, id_especialidad)
    except catalogo.EspecialidadNoEncontrada:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ESPECIALIDAD_NO_ENCONTRADA) from None


@router.get(
    "/profesionales",
    response_model=list[ProfesionalPublico],
    responses=RESPUESTAS_AUTENTICACION | RESPUESTA_404,
)
def listar_profesionales(
    _usuario: UsuarioActual,
    sesion: SesionBD,
    id_especialidad: Annotated[int | None, Query(description="Filtra por especialidad")] = None,
):
    try:
        profesionales = catalogo.listar_profesionales(sesion, id_especialidad)
    except catalogo.EspecialidadNoEncontrada:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ESPECIALIDAD_NO_ENCONTRADA) from None
    return [
        ProfesionalPublico(
            email=p.email,
            nombre=p.nombre,
            apellido=p.apellido,
            matricula=p.matricula,
            id_especialidad=p.id_especialidad,
            especialidad=p.especialidad.nombre,
        )
        for p in profesionales
    ]
