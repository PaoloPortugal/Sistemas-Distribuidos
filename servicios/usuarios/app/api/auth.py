"""Endpoints de auth: registro de pacientes y profesionales, y login."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.esquemas import (
    DatosLogin,
    DatosRegistroPaciente,
    DatosRegistroProfesional,
    Error,
    Token,
    UsuarioPublico,
)
from app.clientes import catalogo
from app.db.sesion import obtener_sesion
from app.dominio import tokens, usuarios

router = APIRouter(tags=["autenticación"])

SesionBD = Annotated[Session, Depends(obtener_sesion)]
Catalogo = Annotated[catalogo.ClienteCatalogo, Depends(catalogo.obtener_cliente_catalogo)]

EMAIL_REGISTRADO = "El email ya está registrado"
DOCUMENTO_REGISTRADO = "El documento ya está registrado"
MATRICULA_REGISTRADA = "La matrícula ya está registrada"
ESPECIALIDAD_INEXISTENTE = "La especialidad no existe"
REGISTRO_NO_DISPONIBLE = "No se pudo completar el registro. Intentá de nuevo más tarde"
CREDENCIALES_INVALIDAS = "Credenciales inválidas"


@router.post(
    "/registro/paciente",
    status_code=status.HTTP_201_CREATED,
    response_model=UsuarioPublico,
    responses={409: {"model": Error, "description": "Email o documento ya registrado"}},
)
def registrar_paciente(datos: DatosRegistroPaciente, sesion: SesionBD):
    try:
        return usuarios.registrar_paciente(sesion, **datos.model_dump())
    except usuarios.EmailYaRegistrado:
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_REGISTRADO) from None
    except usuarios.DocumentoYaRegistrado:
        raise HTTPException(status.HTTP_409_CONFLICT, DOCUMENTO_REGISTRADO) from None


@router.post(
    "/registro/profesional",
    status_code=status.HTTP_201_CREATED,
    response_model=UsuarioPublico,
    responses={
        409: {"model": Error, "description": "Email o matrícula ya registrados"},
        422: {"description": "Datos inválidos o especialidad inexistente"},
        503: {"model": Error, "description": "Catálogo no disponible; no se creó nada"},
    },
)
def registrar_profesional(
    datos: DatosRegistroProfesional, sesion: SesionBD, cliente_catalogo: Catalogo
):
    try:
        return usuarios.registrar_profesional(sesion, cliente_catalogo, **datos.model_dump())
    except (usuarios.EmailYaRegistrado, catalogo.EmailConOtrosDatos):
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_REGISTRADO) from None
    except catalogo.MatriculaYaRegistrada:
        raise HTTPException(status.HTTP_409_CONFLICT, MATRICULA_REGISTRADA) from None
    except catalogo.EspecialidadInexistente:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, ESPECIALIDAD_INEXISTENTE
        ) from None
    except (catalogo.CatalogoNoDisponible, usuarios.RegistroNoCompletado):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, REGISTRO_NO_DISPONIBLE
        ) from None


@router.post(
    "/login",
    response_model=Token,
    responses={401: {"model": Error, "description": CREDENCIALES_INVALIDAS}},
)
def login(datos: DatosLogin, sesion: SesionBD):
    try:
        usuario = usuarios.autenticar(sesion, datos.email, datos.contrasena)
    except usuarios.CredencialesInvalidas:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            CREDENCIALES_INVALIDAS,
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return Token(access_token=tokens.emitir_token(usuario.email, usuario.tipo))
