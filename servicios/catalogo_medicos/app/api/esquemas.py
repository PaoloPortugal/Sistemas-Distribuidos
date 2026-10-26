"""Esquemas de entrada y salida de la API pública de catálogo."""

import datetime

from pydantic import BaseModel, ConfigDict


class EspecialidadPublica(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_especialidad: int
    nombre: str
    descripcion: str | None


class ServicioPublico(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_servicio: int
    nombre: str
    id_especialidad: int


class ProfesionalPublico(BaseModel):
    email: str
    nombre: str
    apellido: str
    matricula: str
    id_especialidad: int
    especialidad: str


class DatosDisponibilidad(BaseModel):
    """El profesional sale del token: no se puede crear una franja para otro."""

    fecha: datetime.date
    horario_inicio: datetime.time
    horario_fin: datetime.time


class DisponibilidadPublica(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_disponibilidad: int
    email_profesional: str
    fecha: datetime.date
    horario_inicio: datetime.time
    horario_fin: datetime.time


class Error(BaseModel):
    detail: str
