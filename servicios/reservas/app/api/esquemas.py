"""Esquemas de entrada y salida de la API de reservas."""

import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class DatosReserva(BaseModel):
    """El paciente sale del token: no se puede reservar a nombre de otro."""

    id_disponibilidad: Annotated[int, Field(gt=0)]
    id_servicio: Annotated[int, Field(gt=0)]


class DatosCancelacion(BaseModel):
    motivo: Annotated[
        str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ] = None


class TurnoPublico(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_turno: int
    estado: str
    email_paciente: str
    email_profesional: str
    id_disponibilidad: int
    id_servicio: int
    fecha: datetime.date
    horario_inicio: datetime.time
    horario_fin: datetime.time
    fecha_creacion: datetime.datetime
    fecha_cancelacion: datetime.datetime | None
    motivo_cancelacion: str | None
    cancelado_por: str | None


class TurnoEnAgenda(TurnoPublico):
    """Turno de la agenda del profesional, con el nombre del paciente (ADR 009)."""

    nombre_paciente: str | None = Field(
        default=None, description="null si el servicio de usuarios no respondió"
    )
    apellido_paciente: str | None = Field(
        default=None, description="null si el servicio de usuarios no respondió"
    )


class Error(BaseModel):
    detail: str
