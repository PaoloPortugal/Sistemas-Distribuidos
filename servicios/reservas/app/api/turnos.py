"""Endpoints de turnos: reservar, cancelar, mis turnos y agenda."""

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.esquemas import DatosCancelacion, DatosReserva, Error, TurnoPublico
from app.api.seguridad import (
    RESPUESTAS_AUTENTICACION,
    RESPUESTAS_PACIENTE,
    RESPUESTAS_PROFESIONAL,
    PacienteActual,
    ProfesionalActual,
    UsuarioActual,
)
from app.clientes import catalogo
from app.db.sesion import obtener_sesion
from app.dominio import reloj, turnos

router = APIRouter(tags=["turnos"])

SesionBD = Annotated[Session, Depends(obtener_sesion)]
Catalogo = Annotated[catalogo.ClienteCatalogo, Depends(catalogo.obtener_cliente_catalogo)]
Ahora = Annotated[datetime.datetime, Depends(reloj.ahora)]

CATALOGO_NO_DISPONIBLE = "El catálogo no está disponible. Intentá de nuevo más tarde"


@router.post(
    "/turnos",
    status_code=status.HTTP_201_CREATED,
    response_model=TurnoPublico,
    responses=RESPUESTAS_PACIENTE
    | {
        404: {"model": Error, "description": "La disponibilidad o el servicio no existen"},
        409: {"model": Error, "description": "El horario ya está reservado"},
        422: {"description": "El servicio no corresponde, o la franja ya pasó"},
        503: {"model": Error, "description": "Catálogo no disponible; no se creó nada"},
    },
)
def reservar(
    datos: DatosReserva,
    paciente: PacienteActual,
    sesion: SesionBD,
    cliente_catalogo: Catalogo,
    ahora: Ahora,
):
    try:
        return turnos.reservar(
            sesion,
            cliente_catalogo,
            email_paciente=paciente.email,
            ahora=ahora,
            **datos.model_dump(),
        )
    except catalogo.DisponibilidadInexistente:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La disponibilidad no existe") from None
    except catalogo.ServicioInexistente:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El servicio no existe") from None
    except catalogo.CatalogoNoDisponible:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, CATALOGO_NO_DISPONIBLE) from None
    except turnos.ServicioNoCorresponde:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "El servicio no corresponde a la especialidad del profesional",
        ) from None
    except turnos.FranjaEnElPasado:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "La franja ya pasó"
        ) from None
    except turnos.HorarioYaReservado:
        raise HTTPException(status.HTTP_409_CONFLICT, "El horario ya está reservado") from None


@router.get(
    "/mis-turnos",
    response_model=list[TurnoPublico],
    responses=RESPUESTAS_PACIENTE,
)
def mis_turnos(paciente: PacienteActual, sesion: SesionBD):
    return turnos.turnos_de_paciente(sesion, paciente.email)


@router.post(
    "/turnos/{id_turno}/cancelar",
    response_model=TurnoPublico,
    responses=RESPUESTAS_AUTENTICACION
    | {
        403: {"model": Error, "description": "El turno no es del paciente ni del profesional"},
        404: {"model": Error, "description": "El turno no existe"},
        409: {"model": Error, "description": "El turno ya no está reservado"},
        422: {"description": "Fuera de plazo (ADR 007)"},
    },
)
def cancelar(
    id_turno: int,
    usuario: UsuarioActual,
    sesion: SesionBD,
    ahora: Ahora,
    datos: DatosCancelacion | None = None,
):
    motivo = datos.motivo if datos else None
    try:
        return turnos.cancelar(
            sesion,
            id_turno=id_turno,
            email=usuario.email,
            tipo=usuario.tipo,
            motivo=motivo,
            ahora=ahora,
        )
    except turnos.TurnoInexistente:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El turno no existe") from None
    except turnos.TurnoAjeno:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El turno no es tuyo") from None
    except turnos.TurnoNoCancelable:
        raise HTTPException(status.HTTP_409_CONFLICT, "El turno ya no está reservado") from None
    except turnos.FueraDePlazo:
        mensaje = (
            "El paciente solo puede cancelar hasta 24 horas antes del turno"
            if usuario.tipo == turnos.PACIENTE
            else "El turno ya empezó"
        )
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, mensaje) from None


@router.get(
    "/agenda",
    response_model=list[TurnoPublico],
    responses=RESPUESTAS_PROFESIONAL | {422: {"description": "Rango de fechas inválido"}},
)
def agenda(
    profesional: ProfesionalActual,
    sesion: SesionBD,
    ahora: Ahora,
    desde: Annotated[
        datetime.date | None, Query(description="Primer día (incluido). Por defecto, hoy.")
    ] = None,
    hasta: Annotated[
        datetime.date | None,
        Query(description="Último día (incluido). Por defecto, 30 días después de 'desde'. Máximo 90 días."),
    ] = None,
):
    try:
        desde, hasta = turnos.resolver_rango(desde, hasta, ahora.date())
    except turnos.RangoInvalido as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return turnos.agenda(sesion, profesional.email, desde, hasta)
