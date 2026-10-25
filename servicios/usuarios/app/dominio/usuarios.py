"""Reglas de negocio de registro y autenticación de usuarios."""

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.clientes.catalogo import CatalogoNoDisponible, ClienteCatalogo, EmailConOtrosDatos
from app.db.modelos import Paciente, Usuario
from app.dominio import contrasenas

PACIENTE = "PACIENTE"
PROFESIONAL = "PROFESIONAL"

registro = logging.getLogger(__name__)


class EmailYaRegistrado(Exception):
    pass


class DocumentoYaRegistrado(Exception):
    pass


class CredencialesInvalidas(Exception):
    pass


class RegistroNoCompletado(Exception):
    """Catálogo creó el profesional pero no se pudo confirmar el usuario."""


def normalizar_email(email: str) -> str:
    return email.strip().lower()


def registrar_paciente(
    sesion: Session,
    *,
    email: str,
    contrasena: str,
    nombre: str,
    apellido: str,
    documento: str,
    telefono: str | None,
) -> Usuario:
    """Crea el usuario y su fila de paciente en una sola transacción."""
    usuario = _nuevo_usuario(email, contrasena, nombre, apellido, PACIENTE)
    usuario.paciente = Paciente(documento=documento, telefono=telefono)
    _insertar(sesion, usuario)
    sesion.commit()
    return usuario


def registrar_profesional(
    sesion: Session,
    catalogo: ClienteCatalogo,
    *,
    email: str,
    contrasena: str,
    nombre: str,
    apellido: str,
    matricula: str,
    id_especialidad: int,
) -> Usuario:
    """Crea el USUARIO aquí y el PROFESIONAL en catalogo_medicos.

    La especialización es total: no puede quedar un USUARIO PROFESIONAL sin
    su PROFESIONAL. Como no hay transacción entre servicios, el USUARIO se
    confirma recién cuando catálogo creó el PROFESIONAL, y si después falla
    la confirmación se compensa borrándolo en catálogo (ADR 002).
    """
    usuario = _nuevo_usuario(email, contrasena, nombre, apellido, PROFESIONAL)
    _insertar(sesion, usuario)

    try:
        catalogo.crear_profesional(usuario.email, matricula, id_especialidad)
    except CatalogoNoDisponible as error:
        sesion.rollback()
        if error.puede_haber_creado:
            _compensar(catalogo, usuario.email)
        raise
    except EmailConOtrosDatos:
        sesion.rollback()
        registro.warning(
            "Catálogo tiene un profesional %s sin usuario y con otros datos", usuario.email
        )
        raise
    except Exception:
        sesion.rollback()
        raise

    try:
        sesion.commit()
    except SQLAlchemyError as error:
        sesion.rollback()
        _compensar(catalogo, usuario.email)
        raise RegistroNoCompletado from error
    return usuario


def autenticar(sesion: Session, email: str, contrasena: str) -> Usuario:
    usuario = sesion.get(Usuario, normalizar_email(email))
    hash_guardado = usuario.contrasena_hash if usuario else None
    if not contrasenas.verificar(hash_guardado, contrasena):
        raise CredencialesInvalidas
    return usuario


def obtener_usuario(sesion: Session, email: str) -> Usuario | None:
    consulta = (
        select(Usuario)
        .where(Usuario.email == normalizar_email(email))
        .options(selectinload(Usuario.paciente))
    )
    return sesion.scalar(consulta)


def _nuevo_usuario(
    email: str, contrasena: str, nombre: str, apellido: str, tipo: str
) -> Usuario:
    return Usuario(
        email=normalizar_email(email),
        contrasena_hash=contrasenas.hashear(contrasena),
        nombre=nombre,
        apellido=apellido,
        tipo=tipo,
    )


def _insertar(sesion: Session, usuario: Usuario) -> None:
    """Envía el usuario a la base sin confirmar; los duplicados los detecta PostgreSQL.

    No se consulta antes de insertar: dos registros simultáneos podrían pasar
    la consulta. Si la base rechaza el insert, se averigua qué dato chocó.
    """
    sesion.add(usuario)
    try:
        sesion.flush()
    except IntegrityError:
        sesion.rollback()
        if sesion.get(Usuario, usuario.email) is not None:
            raise EmailYaRegistrado from None
        if usuario.paciente is not None and _documento_registrado(
            sesion, usuario.paciente.documento
        ):
            raise DocumentoYaRegistrado from None
        raise


def _documento_registrado(sesion: Session, documento: str) -> bool:
    consulta = select(Paciente.email).where(Paciente.documento == documento)
    return sesion.scalar(consulta) is not None


def _compensar(catalogo: ClienteCatalogo, email: str) -> None:
    """Borra en catálogo el profesional de un registro que no se completó."""
    try:
        catalogo.borrar_profesional(email)
    except Exception:
        registro.exception(
            "Inconsistencia: no se pudo compensar; el profesional %s puede haber "
            "quedado en catálogo sin usuario",
            email,
        )
