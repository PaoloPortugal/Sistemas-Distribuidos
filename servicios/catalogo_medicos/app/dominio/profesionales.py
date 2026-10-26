"""Alta y baja de profesionales pedidas por el servicio de usuarios (ADR 002).

Ambas operaciones son idempotentes por email, para que usuarios pueda
reintentar o compensar después de un timeout sin riesgo.
"""

from enum import Enum

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.modelos import Disponibilidad, Especialidad, Profesional


class ResultadoAlta(Enum):
    CREADO = "creado"
    YA_EXISTIA = "ya_existia"


class MatriculaDuplicada(Exception):
    pass


class EmailConOtrosDatos(Exception):
    pass


class EspecialidadInexistente(Exception):
    pass


class ProfesionalConDisponibilidades(Exception):
    pass


def normalizar_email(email: str) -> str:
    return email.strip().lower()


def crear_profesional(
    sesion: Session,
    *,
    email: str,
    matricula: str,
    id_especialidad: int,
    nombre: str,
    apellido: str,
) -> tuple[Profesional, ResultadoAlta]:
    """Crea el profesional; si ya existe con los mismos datos, no es un error.

    "Los mismos datos" son matrícula y especialidad. Nombre y apellido son una
    copia para mostrar (ADR 004): en un reintento se actualizan sin que cuente
    como conflicto.

    No se consulta antes de insertar: los conflictos los detecta PostgreSQL
    (PK del email, UNIQUE de la matrícula, FK de la especialidad) y después se
    averigua cuál fue.
    """
    profesional = Profesional(
        email=normalizar_email(email),
        matricula=matricula,
        id_especialidad=id_especialidad,
        nombre=nombre,
        apellido=apellido,
    )
    sesion.add(profesional)
    try:
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        existente = sesion.get(Profesional, profesional.email)
        if existente is not None:
            if (existente.matricula, existente.id_especialidad) == (matricula, id_especialidad):
                existente.nombre, existente.apellido = nombre, apellido
                sesion.commit()
                return existente, ResultadoAlta.YA_EXISTIA
            raise EmailConOtrosDatos from None
        if _matricula_registrada(sesion, matricula):
            raise MatriculaDuplicada from None
        if sesion.get(Especialidad, id_especialidad) is None:
            raise EspecialidadInexistente from None
        raise
    return profesional, ResultadoAlta.CREADO


def borrar_profesional(sesion: Session, email: str) -> None:
    """Borra el profesional; si no existe, no es un error.

    Si tiene disponibilidades, la FK con RESTRICT impide borrarlo.
    """
    email = normalizar_email(email)
    profesional = sesion.get(Profesional, email)
    if profesional is None:
        return
    sesion.delete(profesional)
    try:
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        if _tiene_disponibilidades(sesion, email):
            raise ProfesionalConDisponibilidades from None
        raise


def _matricula_registrada(sesion: Session, matricula: str) -> bool:
    consulta = select(Profesional.email).where(Profesional.matricula == matricula)
    return sesion.scalar(consulta) is not None


def _tiene_disponibilidades(sesion: Session, email: str) -> bool:
    consulta = select(Disponibilidad.id_disponibilidad).where(
        Disponibilidad.email_profesional == email
    )
    return sesion.scalar(consulta.limit(1)) is not None
