"""Registro de profesional: USUARIO en usuarios y PROFESIONAL en catálogo (ADR 002)."""

import logging

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.clientes.catalogo import (
    CatalogoNoDisponible,
    EmailConOtrosDatos,
    EspecialidadInexistente,
    MatriculaYaRegistrada,
)
from app.db.modelos import Paciente, Usuario
from app.db.sesion import obtener_sesion
from app.main import app
from tests.conftest import datos_paciente, datos_profesional

NO_DISPONIBLE = "No se pudo completar el registro. Intentá de nuevo más tarde"


def usuario_existe(fabrica_sesiones, email: str) -> bool:
    with fabrica_sesiones() as sesion:
        return sesion.get(Usuario, email) is not None


def test_exitoso_crea_usuario_y_profesional_en_catalogo(cliente, catalogo, fabrica_sesiones):
    respuesta = cliente.post(
        "/registro/profesional", json=datos_profesional(email="Dr.Gomez@Ejemplo.com")
    )

    assert respuesta.status_code == 201
    assert respuesta.json() == {
        "email": "dr.gomez@ejemplo.com",
        "nombre": "Bruno",
        "apellido": "Gómez",
        "tipo": "PROFESIONAL",
        "paciente": None,
    }
    assert catalogo.creados == [
        {
            "email": "dr.gomez@ejemplo.com",
            "matricula": "MP-12345",
            "id_especialidad": 1,
            "nombre": "Bruno",
            "apellido": "Gómez",
        }
    ]
    assert catalogo.borrados == []
    with fabrica_sesiones() as sesion:
        assert sesion.get(Usuario, "dr.gomez@ejemplo.com").tipo == "PROFESIONAL"
        assert sesion.get(Paciente, "dr.gomez@ejemplo.com") is None


def test_email_duplicado_no_llama_a_catalogo(cliente, catalogo):
    cliente.post("/registro/paciente", json=datos_paciente(email="compartido@ejemplo.com"))

    respuesta = cliente.post(
        "/registro/profesional", json=datos_profesional(email="compartido@ejemplo.com")
    )

    assert respuesta.status_code == 409
    assert respuesta.json() == {"detail": "El email ya está registrado"}
    assert catalogo.creados == []


def test_catalogo_matricula_duplicada(cliente, catalogo, fabrica_sesiones):
    catalogo.error_al_crear = MatriculaYaRegistrada()

    respuesta = cliente.post("/registro/profesional", json=datos_profesional())

    assert respuesta.status_code == 409
    assert respuesta.json() == {"detail": "La matrícula ya está registrada"}
    assert not usuario_existe(fabrica_sesiones, "dr.gomez@ejemplo.com")
    assert catalogo.borrados == []


def test_catalogo_especialidad_inexistente(cliente, catalogo, fabrica_sesiones):
    catalogo.error_al_crear = EspecialidadInexistente()

    respuesta = cliente.post(
        "/registro/profesional", json=datos_profesional(id_especialidad=999)
    )

    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": "La especialidad no existe"}
    assert not usuario_existe(fabrica_sesiones, "dr.gomez@ejemplo.com")
    assert catalogo.borrados == []


def test_catalogo_con_otro_profesional_en_ese_email(cliente, catalogo, fabrica_sesiones):
    catalogo.error_al_crear = EmailConOtrosDatos()

    respuesta = cliente.post("/registro/profesional", json=datos_profesional())

    assert respuesta.status_code == 409
    assert respuesta.json() == {"detail": "El email ya está registrado"}
    assert not usuario_existe(fabrica_sesiones, "dr.gomez@ejemplo.com")
    # No es nuestro: no se borra.
    assert catalogo.borrados == []


def test_catalogo_caido_no_queda_usuario(cliente, catalogo, fabrica_sesiones):
    catalogo.error_al_crear = CatalogoNoDisponible("conexión rechazada", puede_haber_creado=False)

    respuesta = cliente.post("/registro/profesional", json=datos_profesional())

    assert respuesta.status_code == 503
    assert respuesta.json() == {"detail": NO_DISPONIBLE}
    assert not usuario_existe(fabrica_sesiones, "dr.gomez@ejemplo.com")
    # El pedido no llegó: no hace falta compensar.
    assert catalogo.borrados == []


def test_catalogo_timeout_no_queda_usuario_y_compensa(cliente, catalogo, fabrica_sesiones):
    catalogo.error_al_crear = CatalogoNoDisponible("timeout de lectura", puede_haber_creado=True)

    respuesta = cliente.post("/registro/profesional", json=datos_profesional())

    assert respuesta.status_code == 503
    assert not usuario_existe(fabrica_sesiones, "dr.gomez@ejemplo.com")
    # Catálogo pudo haberlo creado aunque no respondió: se borra por las dudas.
    assert catalogo.borrados == ["dr.gomez@ejemplo.com"]


def test_despues_se_puede_registrar_cuando_catalogo_vuelve(cliente, catalogo):
    catalogo.error_al_crear = CatalogoNoDisponible("timeout", puede_haber_creado=True)
    assert cliente.post("/registro/profesional", json=datos_profesional()).status_code == 503

    catalogo.error_al_crear = None
    respuesta = cliente.post("/registro/profesional", json=datos_profesional())

    assert respuesta.status_code == 201


class SesionQueFallaAlConfirmar(Session):
    def commit(self):
        raise OperationalError("COMMIT", {}, Exception("se perdió la conexión"))


@pytest.fixture
def commit_falla(motor):
    def sesion_que_falla():
        with SesionQueFallaAlConfirmar(bind=motor, autoflush=False) as sesion:
            yield sesion

    app.dependency_overrides[obtener_sesion] = sesion_que_falla


def test_falla_el_commit_despues_de_crear_en_catalogo_compensa(
    cliente, catalogo, commit_falla, fabrica_sesiones
):
    respuesta = cliente.post("/registro/profesional", json=datos_profesional())

    assert respuesta.status_code == 503
    assert catalogo.creados == [
        {
            "email": "dr.gomez@ejemplo.com",
            "matricula": "MP-12345",
            "id_especialidad": 1,
            "nombre": "Bruno",
            "apellido": "Gómez",
        }
    ]
    assert catalogo.borrados == ["dr.gomez@ejemplo.com"]
    assert not usuario_existe(fabrica_sesiones, "dr.gomez@ejemplo.com")


def test_falla_el_commit_y_la_compensacion_queda_registrada(
    cliente, catalogo, commit_falla, caplog
):
    catalogo.error_al_borrar = CatalogoNoDisponible("timeout", puede_haber_creado=True)

    with caplog.at_level(logging.ERROR, logger="app.dominio.usuarios"):
        respuesta = cliente.post("/registro/profesional", json=datos_profesional())

    assert respuesta.status_code == 503
    assert catalogo.borrados == ["dr.gomez@ejemplo.com"]
    assert "Inconsistencia" in caplog.text
    assert "dr.gomez@ejemplo.com" in caplog.text


@pytest.mark.parametrize(
    "cambios",
    [
        {"contrasena": "corta"},
        {"matricula": "  "},
        {"id_especialidad": 0},
        {"id_especialidad": "cardiología"},
    ],
    ids=["contrasena-corta", "matricula-vacia", "especialidad-cero", "especialidad-no-numerica"],
)
def test_datos_invalidos_no_llaman_a_catalogo(cliente, catalogo, cambios):
    respuesta = cliente.post("/registro/profesional", json=datos_profesional(**cambios))

    assert respuesta.status_code == 422
    assert catalogo.creados == []


def test_faltan_matricula_y_especialidad(cliente, catalogo):
    datos = datos_profesional()
    del datos["matricula"], datos["id_especialidad"]

    assert cliente.post("/registro/profesional", json=datos).status_code == 422
    assert catalogo.creados == []
