"""Interpretación de los eventos turno.confirmado y turno.cancelado.

Contrato en docs/05-comunicacion.md. Un mensaje que no cumple el contrato es
inválido: va a la dead-letter queue, no se reintenta (ADR 008).
"""

import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, ValidationError, model_validator

TURNO_CONFIRMADO = "turno.confirmado"
TURNO_CANCELADO = "turno.cancelado"


class EventoInvalido(Exception):
    pass


class EventoTurno(BaseModel):
    id_evento: uuid.UUID
    tipo: Literal["turno.confirmado", "turno.cancelado"]
    ocurrido_en: datetime.datetime
    id_turno: int
    id_disponibilidad: int
    id_servicio: int
    email_paciente: EmailStr
    email_profesional: EmailStr
    fecha: datetime.date
    horario_inicio: datetime.time
    horario_fin: datetime.time
    cancelado_por: Literal["PACIENTE", "PROFESIONAL"] | None = None
    motivo: str | None = None

    @model_validator(mode="after")
    def cancelacion_completa(self) -> "EventoTurno":
        if self.tipo == TURNO_CANCELADO and self.cancelado_por is None:
            raise ValueError("turno.cancelado sin cancelado_por")
        return self


def interpretar(cuerpo: bytes) -> EventoTurno:
    try:
        return EventoTurno.model_validate_json(cuerpo)
    except ValidationError as error:
        raise EventoInvalido(str(error)) from error
