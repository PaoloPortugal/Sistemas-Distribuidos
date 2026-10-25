"""Esquemas de entrada y salida de la API de usuarios."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

# La contraseña no se recorta: los espacios son parte de ella.
Contrasena = Annotated[str, Field(min_length=8, max_length=128)]
Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Documento = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
Telefono = Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)]
Matricula = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]


class DatosRegistroUsuario(BaseModel):
    email: EmailStr
    contrasena: Contrasena
    nombre: Nombre
    apellido: Nombre


class DatosRegistroPaciente(DatosRegistroUsuario):
    documento: Documento
    telefono: Telefono | None = None


class DatosRegistroProfesional(DatosRegistroUsuario):
    """Matrícula y especialidad se guardan en catalogo_medicos, no en usuarios."""

    matricula: Matricula
    id_especialidad: Annotated[int, Field(gt=0)]


class DatosLogin(BaseModel):
    email: Annotated[str, Field(max_length=254)]
    contrasena: Annotated[str, Field(max_length=128)]


class DatosPaciente(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    documento: str
    telefono: str | None


class UsuarioPublico(BaseModel):
    """Datos de un usuario que se pueden mostrar (nunca el hash)."""

    model_config = ConfigDict(from_attributes=True)

    email: str
    nombre: str
    apellido: str
    tipo: str
    paciente: DatosPaciente | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class Error(BaseModel):
    detail: str
