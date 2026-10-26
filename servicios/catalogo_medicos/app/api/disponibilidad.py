"""Endpoints de disponibilidad: franjas horarias de los profesionales.

Todavía no indican qué franjas están libres: eso depende de reservas (ADR 003).
"""

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.esquemas import DatosDisponibilidad, DisponibilidadPublica, Error
from app.api.seguridad import (
    RESPUESTAS_AUTENTICACION,
    RESPUESTAS_PROFESIONAL,
    ProfesionalActual,
    UsuarioActual,
)
from app.db.sesion import obtener_sesion
from app.dominio import catalogo, disponibilidades, reloj

router = APIRouter(tags=["disponibilidad"])

SesionBD = Annotated[Session, Depends(obtener_sesion)]
Ahora = Annotated[datetime.datetime, Depends(reloj.ahora)]
Desde = Annotated[
    datetime.date | None, Query(description="Primer día (incluido). Por defecto, hoy.")
]
Hasta = Annotated[
    datetime.date | None,
    Query(description="Último día (incluido). Por defecto, 30 días después de 'desde'. Máximo 90 días."),
]

PROFESIONAL_NO_ENCONTRADO = "El profesional no existe"
NO_ES_PROFESIONAL_DEL_CATALOGO = "El usuario no está registrado como profesional en el catálogo"


@router.get(
    "/profesionales/{email}/disponibilidades",
    response_model=list[DisponibilidadPublica],
    responses=RESPUESTAS_AUTENTICACION
    | {
        404: {"model": Error, "description": PROFESIONAL_NO_ENCONTRADO},
        422: {"description": "Rango de fechas inválido"},
    },
)
def listar_de_profesional(
    email: str,
    _usuario: UsuarioActual,
    sesion: SesionBD,
    ahora: Ahora,
    desde: Desde = None,
    hasta: Hasta = None,
):
    if catalogo.obtener_profesional(sesion, email) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, PROFESIONAL_NO_ENCONTRADO)
    desde, hasta = _rango(desde, hasta, ahora)
    return disponibilidades.listar_disponibilidades(sesion, email, desde, hasta)


@router.post(
    "/disponibilidades",
    status_code=status.HTTP_201_CREATED,
    response_model=DisponibilidadPublica,
    responses=RESPUESTAS_PROFESIONAL
    | {
        409: {"model": Error, "description": "Se superpone con otra franja del profesional"},
        422: {"description": "Inicio no anterior al fin, o franja en el pasado"},
    },
)
def crear(datos: DatosDisponibilidad, profesional: ProfesionalActual, sesion: SesionBD, ahora: Ahora):
    try:
        return disponibilidades.crear_disponibilidad(
            sesion, email_profesional=profesional.email, ahora=ahora, **datos.model_dump()
        )
    except disponibilidades.HorarioInvalido:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "El horario de inicio tiene que ser anterior al de fin",
        ) from None
    except disponibilidades.FranjaEnElPasado:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "No se pueden crear franjas en el pasado",
        ) from None
    except disponibilidades.FranjaSuperpuesta as error:
        existente = error.existente
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Se superpone con la franja del {existente.fecha:%Y-%m-%d} de "
            f"{existente.horario_inicio:%H:%M} a {existente.horario_fin:%H:%M}",
        ) from None
    except disponibilidades.ProfesionalNoRegistrado:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NO_ES_PROFESIONAL_DEL_CATALOGO) from None


@router.get(
    "/mis-disponibilidades",
    response_model=list[DisponibilidadPublica],
    responses=RESPUESTAS_PROFESIONAL | {422: {"description": "Rango de fechas inválido"}},
)
def listar_propias(
    profesional: ProfesionalActual,
    sesion: SesionBD,
    ahora: Ahora,
    desde: Desde = None,
    hasta: Hasta = None,
):
    if catalogo.obtener_profesional(sesion, profesional.email) is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NO_ES_PROFESIONAL_DEL_CATALOGO)
    desde, hasta = _rango(desde, hasta, ahora)
    return disponibilidades.listar_disponibilidades(sesion, profesional.email, desde, hasta)


def _rango(
    desde: datetime.date | None, hasta: datetime.date | None, ahora: datetime.datetime
) -> tuple[datetime.date, datetime.date]:
    try:
        return disponibilidades.resolver_rango(desde, hasta, ahora.date())
    except disponibilidades.RangoInvalido as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
