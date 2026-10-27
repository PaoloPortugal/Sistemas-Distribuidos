"""Endpoints internos: los usa catálogo, no el cliente web (ADR 003).

Contrato en docs/05-comunicacion.md. Traefik no publica /interno.
"""

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.sesion import obtener_sesion
from app.dominio import bloqueos, reloj

router = APIRouter(prefix="/interno", tags=["interno"])

SesionBD = Annotated[Session, Depends(obtener_sesion)]
Ahora = Annotated[datetime.datetime, Depends(reloj.ahora)]


class ConsultaOcupadas(BaseModel):
    ids: Annotated[list[int], Field(max_length=bloqueos.MAXIMO_IDS)]


class Ocupadas(BaseModel):
    ocupadas: list[int]


class ErrorInterno(BaseModel):
    detail: str
    codigo: str


@router.post("/disponibilidades-ocupadas", response_model=Ocupadas)
def disponibilidades_ocupadas(consulta: ConsultaOcupadas, sesion: SesionBD):
    """De los ids recibidos, los que tienen un turno RESERVADO o están bloqueados."""
    return Ocupadas(ocupadas=bloqueos.ocupadas(sesion, consulta.ids))


@router.put(
    "/bloqueos/{id_disponibilidad}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={409: {"model": ErrorInterno, "description": "DISPONIBILIDAD_CON_TURNO"}},
)
def bloquear(id_disponibilidad: int, sesion: SesionBD, ahora: Ahora):
    try:
        bloqueos.bloquear(sesion, id_disponibilidad, ahora)
    except bloqueos.DisponibilidadConTurno:
        return JSONResponse(
            {"detail": "El horario tiene un turno reservado", "codigo": "DISPONIBILIDAD_CON_TURNO"},
            status_code=status.HTTP_409_CONFLICT,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/bloqueos/{id_disponibilidad}", status_code=status.HTTP_204_NO_CONTENT)
def desbloquear(id_disponibilidad: int, sesion: SesionBD):
    bloqueos.desbloquear(sesion, id_disponibilidad)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
