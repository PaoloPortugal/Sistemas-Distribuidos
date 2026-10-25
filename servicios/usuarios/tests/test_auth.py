from datetime import UTC, datetime
from pathlib import Path

import jwt
import pytest

from app.config import configuracion
from app.db.modelos import Paciente, Usuario
from tests.conftest import CONTRASENA, datos_paciente, datos_profesional


# --- Registro de paciente ---


def test_registro_paciente_exitoso(cliente, fabrica_sesiones):
    respuesta = cliente.post(
        "/registro/paciente", json=datos_paciente(email="Ana.Perez@Ejemplo.COM")
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo == {
        "email": "ana.perez@ejemplo.com",
        "nombre": "Ana",
        "apellido": "Pérez",
        "tipo": "PACIENTE",
        "paciente": {"documento": "12345678", "telefono": "099123456"},
    }
    with fabrica_sesiones() as sesion:
        usuario = sesion.get(Usuario, "ana.perez@ejemplo.com")
        assert usuario.contrasena_hash.startswith("$argon2id$")
        assert CONTRASENA not in usuario.contrasena_hash
        assert sesion.get(Paciente, "ana.perez@ejemplo.com").documento == "12345678"


def test_registro_paciente_sin_telefono(cliente):
    datos = datos_paciente()
    del datos["telefono"]

    respuesta = cliente.post("/registro/paciente", json=datos)

    assert respuesta.status_code == 201
    assert respuesta.json()["paciente"] == {"documento": "12345678", "telefono": None}


def test_registro_paciente_email_duplicado(cliente):
    cliente.post("/registro/paciente", json=datos_paciente())

    respuesta = cliente.post(
        "/registro/paciente",
        json=datos_paciente(email="ANA.PEREZ@ejemplo.com", documento="99999999"),
    )

    assert respuesta.status_code == 409
    assert respuesta.json() == {"detail": "El email ya está registrado"}


def test_registro_paciente_documento_duplicado_no_crea_usuario(cliente, fabrica_sesiones):
    cliente.post("/registro/paciente", json=datos_paciente())

    respuesta = cliente.post(
        "/registro/paciente", json=datos_paciente(email="otra@ejemplo.com")
    )

    assert respuesta.status_code == 409
    assert respuesta.json() == {"detail": "El documento ya está registrado"}
    with fabrica_sesiones() as sesion:
        # Transacción única: si falla el paciente, tampoco queda el usuario.
        assert sesion.get(Usuario, "otra@ejemplo.com") is None


@pytest.mark.parametrize(
    "cambios",
    [
        {"email": "no-es-un-email"},
        {"contrasena": "corta"},
        {"nombre": "   "},
        {"documento": ""},
        {"documento": "1" * 21},
    ],
    ids=["email-invalido", "contrasena-corta", "nombre-vacio", "documento-vacio", "documento-largo"],
)
def test_registro_paciente_datos_invalidos(cliente, cambios):
    respuesta = cliente.post("/registro/paciente", json=datos_paciente(**cambios))

    assert respuesta.status_code == 422


def test_registro_paciente_sin_documento(cliente):
    datos = datos_paciente()
    del datos["documento"]

    assert cliente.post("/registro/paciente", json=datos).status_code == 422


def test_registro_paciente_ignora_tipo_enviado(cliente):
    respuesta = cliente.post(
        "/registro/paciente", json=datos_paciente(tipo="PROFESIONAL")
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["tipo"] == "PACIENTE"


# --- Login ---


def test_login_exitoso_devuelve_jwt_rs256(cliente, rutas_claves):
    cliente.post("/registro/paciente", json=datos_paciente())

    respuesta = cliente.post(
        "/login", json={"email": "Ana.Perez@ejemplo.com", "contrasena": CONTRASENA}
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["token_type"] == "bearer"
    assert jwt.get_unverified_header(cuerpo["access_token"])["alg"] == "RS256"
    claims = jwt.decode(
        cuerpo["access_token"],
        Path(rutas_claves[1]).read_text(),
        algorithms=["RS256"],
        issuer="usuarios",
    )
    assert claims["sub"] == "ana.perez@ejemplo.com"
    assert claims["tipo"] == "PACIENTE"
    duracion = claims["exp"] - claims["iat"]
    assert duracion == configuracion.duracion_token_minutos * 60
    assert claims["exp"] > datetime.now(UTC).timestamp()


def test_login_profesional_lleva_su_tipo(cliente, rutas_claves):
    cliente.post("/registro/profesional", json=datos_profesional())

    respuesta = cliente.post(
        "/login", json={"email": "dr.gomez@ejemplo.com", "contrasena": CONTRASENA}
    )

    claims = jwt.decode(
        respuesta.json()["access_token"],
        Path(rutas_claves[1]).read_text(),
        algorithms=["RS256"],
        issuer="usuarios",
    )
    assert claims["tipo"] == "PROFESIONAL"


def test_login_contrasena_incorrecta(cliente):
    cliente.post("/registro/paciente", json=datos_paciente())

    respuesta = cliente.post(
        "/login", json={"email": "ana.perez@ejemplo.com", "contrasena": "otra-clave-999"}
    )

    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": "Credenciales inválidas"}
    assert respuesta.headers["www-authenticate"] == "Bearer"


def test_login_email_inexistente_mismo_mensaje(cliente):
    respuesta = cliente.post(
        "/login", json={"email": "nadie@ejemplo.com", "contrasena": CONTRASENA}
    )

    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": "Credenciales inválidas"}


def test_login_sin_contrasena(cliente):
    respuesta = cliente.post("/login", json={"email": "ana.perez@ejemplo.com"})

    assert respuesta.status_code == 422
