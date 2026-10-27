"""Endpoints de disponibilidad: franjas horarias de los profesionales.

Los listados marcan qué franjas están libres consultando a reservas, y
borrar una franja le pide a reservas que la bloquee (ADR 003). Modificar una
franja es borrarla y crear otra.
"""

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.esquemas import DatosDisponibilidad, DisponibilidadConEstado, DisponibilidadPublica, Error
from app.api.seguridad import (
    RESPUESTAS_AUTENTICACION,
    RESPUESTAS_PROFESIONAL,
    ProfesionalActual,
    UsuarioActual,
)
from app.clientes import reservas
from app.db.modelos import Disponibilidad
from app.db.sesion import obtener_sesion
from app.dominio import catalogo, disponibilidades, reloj

router = APIRouter(tags=["disponibilidad"])

SesionBD = Annotated[Session, Depends(obtener_sesion)]
Reservas = Annotated[reservas.ClienteReservas, Depends(reservas.obtener_cliente_reservas)]
Ahora = Annotated[datetime.datetime, Depends(reloj.ahora)]
Desde = Annotated[
    datetime.date | None, Query(description="Primer día (incluido). Por defecto, hoy.")
]
Hasta = Annotated[
    datetime.date | None,
    Query(description="Último día (incluido). Por defecto, 30 días después de 'desde'. Máximo 90 días."),
]
SoloLibres = Annotated[
    bool, Query(description="Solo las franjas libres. Responde 503 si reservas no responde.")
]

PROFESIONAL_NO_ENCONTRADO = "El profesional no existe"
NO_ES_PROFESIONAL_DEL_CATALOGO = "El usuario no está registrado como profesional en el catálogo"
RESERVAS_NO_DISPONIBLE = "El servicio de reservas no está disponible. Intentá de nuevo más tarde"
RESPUESTAS_LISTADO = {
    422: {"description": "Rango de fechas inválido"},
    503: {"model": Error, "description": "Con solo_libres, reservas no respondió"},
}


@router.get(
    "/profesionales/{email}/disponibilidades",
    response_model=list[DisponibilidadConEstado],
    responses=RESPUESTAS_AUTENTICACION
    | RESPUESTAS_LISTADO
    | {404: {"model": Error, "description": PROFESIONAL_NO_ENCONTRADO}},
)
def listar_de_profesional(
    email: str,
    _usuario: UsuarioActual,
    sesion: SesionBD,
    cliente_reservas: Reservas,
    ahora: Ahora,
    desde: Desde = None,
    hasta: Hasta = None,
    solo_libres: SoloLibres = False,
):
    if catalogo.obtener_profesional(sesion, email) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, PROFESIONAL_NO_ENCONTRADO)
    desde, hasta = _rango(desde, hasta, ahora)
    franjas = disponibilidades.listar_disponibilidades(sesion, email, desde, hasta)
    return _con_estado(franjas, cliente_reservas, ahora, solo_libres)


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


@router.delete(
    "/disponibilidades/{id_disponibilidad}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=RESPUESTAS_PROFESIONAL
    | {
        404: {"model": Error, "description": "La franja no existe"},
        409: {"model": Error, "description": "La franja tiene un turno reservado"},
        422: {"model": Error, "description": "La franja ya empezó"},
        503: {"model": Error, "description": "Reservas no disponible; no se borró nada"},
    },
)
def eliminar(
    id_disponibilidad: int,
    profesional: ProfesionalActual,
    sesion: SesionBD,
    cliente_reservas: Reservas,
    ahora: Ahora,
):
    try:
        disponibilidades.eliminar_disponibilidad(
            sesion,
            cliente_reservas,
            id_disponibilidad=id_disponibilidad,
            email_profesional=profesional.email,
            ahora=ahora,
        )
    except disponibilidades.DisponibilidadNoEncontrada:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La franja no existe") from None
    except disponibilidades.DisponibilidadAjena:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "La franja no es tuya") from None
    except disponibilidades.FranjaYaEmpezo:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "No se puede borrar una franja que ya empezó"
        ) from None
    except reservas.DisponibilidadConTurno:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La franja tiene un turno reservado: hay que cancelarlo antes de borrarla",
        ) from None
    except reservas.ReservasNoDisponible:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, RESERVAS_NO_DISPONIBLE) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/disponibilidades/{id_disponibilidad}",
    response_model=DisponibilidadPublica,
    responses=RESPUESTAS_PROFESIONAL
    | {
        404: {"model": Error, "description": "La franja no existe"},
        409: {"model": Error, "description": "Se superpone con otra franja"},
        422: {"model": Error, "description": "La franja ya empezó o el horario es inválido"},
    },
)
def modificar(
    id_disponibilidad: int,
    datos: DatosDisponibilidad,
    profesional: ProfesionalActual,
    sesion: SesionBD,
    ahora: Ahora,
):
    try:
        return disponibilidades.modificar_disponibilidad(
            sesion,
            id_disponibilidad=id_disponibilidad,
            email_profesional=profesional.email,
            ahora=ahora,
            **datos.model_dump(),
        )
    except disponibilidades.DisponibilidadNoEncontrada:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La franja no existe") from None
    except disponibilidades.DisponibilidadAjena:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "La franja no es tuya") from None
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


@router.get(
    "/mis-disponibilidades",
    response_model=list[DisponibilidadConEstado],
    responses=RESPUESTAS_PROFESIONAL | RESPUESTAS_LISTADO,
)
def listar_propias(
    profesional: ProfesionalActual,
    sesion: SesionBD,
    cliente_reservas: Reservas,
    ahora: Ahora,
    desde: Desde = None,
    hasta: Hasta = None,
    solo_libres: SoloLibres = False,
):
    if catalogo.obtener_profesional(sesion, profesional.email) is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NO_ES_PROFESIONAL_DEL_CATALOGO)
    desde, hasta = _rango(desde, hasta, ahora)
    franjas = disponibilidades.listar_disponibilidades(sesion, profesional.email, desde, hasta)
    return _con_estado(franjas, cliente_reservas, ahora, solo_libres)


def _con_estado(
    franjas: list[Disponibilidad],
    cliente_reservas: reservas.ClienteReservas,
    ahora: datetime.datetime,
    solo_libres: bool,
) -> list[DisponibilidadConEstado]:
    marcadas = disponibilidades.marcar_libres(franjas, cliente_reservas, ahora)
    if solo_libres:
        if any(libre is None for _, libre in marcadas):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, RESERVAS_NO_DISPONIBLE)
        marcadas = [(d, libre) for d, libre in marcadas if libre]
    return [
        DisponibilidadConEstado(
            **DisponibilidadPublica.model_validate(d).model_dump(), libre=libre
        )
        for d, libre in marcadas
    ]


def _rango(
    desde: datetime.date | None, hasta: datetime.date | None, ahora: datetime.datetime
) -> tuple[datetime.date, datetime.date]:
    try:
        return disponibilidades.resolver_rango(desde, hasta, ahora.date())
    except disponibilidades.RangoInvalido as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
