"""Endpoints internos para reservas: nombre y apellido de los pacientes (ADR 009)."""

import pytest

from tests.conftest import datos_paciente, datos_profesional


@pytest.fixture
def registrados(cliente) -> None:
    cliente.post("/registro/paciente", json=datos_paciente())
    cliente.post(
        "/registro/paciente",
        json=datos_paciente(email="beto.diaz@ejemplo.com", nombre="Beto", apellido="Díaz",
                            documento="87654321"),
    )
    cliente.post("/registro/profesional", json=datos_profesional())


# --- GET /interno/usuarios/{email} ---


def test_datos_de_un_usuario(cliente, registrados):
    respuesta = cliente.get("/interno/usuarios/ana.perez@ejemplo.com")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"email": "ana.perez@ejemplo.com", "nombre": "Ana", "apellido": "Pérez"}


def test_usuario_inexistente_responde_404(cliente, registrados):
    respuesta = cliente.get("/interno/usuarios/nadie@ejemplo.com")

    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "Usuario no encontrado", "codigo": "USUARIO_INEXISTENTE"}


@pytest.mark.parametrize(
    "ruta",
    ["/interno/usuarios/ana.perez%40ejemplo.com", "/interno/usuarios/Ana.Perez%40Ejemplo.COM"],
    ids=["arroba-codificada", "mayusculas"],
)
def test_email_codificado_o_en_mayusculas(cliente, registrados, ruta):
    respuesta = cliente.get(ruta)

    assert respuesta.status_code == 200
    assert respuesta.json()["email"] == "ana.perez@ejemplo.com"


def test_no_devuelve_datos_sensibles(cliente, registrados):
    respuesta = cliente.get("/interno/usuarios/ana.perez@ejemplo.com")

    assert set(respuesta.json()) == {"email", "nombre", "apellido"}


# --- POST /interno/usuarios/nombres ---


def test_nombres_de_varios_usuarios(cliente, registrados):
    respuesta = cliente.post(
        "/interno/usuarios/nombres",
        json={"emails": ["beto.diaz@ejemplo.com", "ANA.PEREZ@ejemplo.com", "nadie@ejemplo.com"]},
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "usuarios": [
            {"email": "ana.perez@ejemplo.com", "nombre": "Ana", "apellido": "Pérez"},
            {"email": "beto.diaz@ejemplo.com", "nombre": "Beto", "apellido": "Díaz"},
        ]
    }


def test_nombres_sin_emails(cliente):
    respuesta = cliente.post("/interno/usuarios/nombres", json={"emails": []})

    assert respuesta.json() == {"usuarios": []}


def test_nombres_con_mas_de_1000_emails_responde_422(cliente):
    emails = [f"p{i}@ejemplo.com" for i in range(1001)]

    assert cliente.post("/interno/usuarios/nombres", json={"emails": emails}).status_code == 422
