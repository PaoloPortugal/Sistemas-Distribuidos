from datetime import UTC, datetime, timedelta

import jwt

from app.db.modelos import Usuario
from app.dominio import tokens
from tests.conftest import CONTRASENA, datos_paciente, datos_profesional, generar_par_claves


def iniciar_sesion(cliente, email: str) -> dict:
    respuesta = cliente.post("/login", json={"email": email, "contrasena": CONTRASENA})
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


def test_yo_paciente(cliente):
    cliente.post("/registro/paciente", json=datos_paciente())

    respuesta = cliente.get("/yo", headers=iniciar_sesion(cliente, "ana.perez@ejemplo.com"))

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "email": "ana.perez@ejemplo.com",
        "nombre": "Ana",
        "apellido": "Pérez",
        "tipo": "PACIENTE",
        "paciente": {"documento": "12345678", "telefono": "099123456"},
    }


def test_yo_profesional(cliente):
    cliente.post("/registro/profesional", json=datos_profesional())

    respuesta = cliente.get("/yo", headers=iniciar_sesion(cliente, "dr.gomez@ejemplo.com"))

    assert respuesta.status_code == 200
    assert respuesta.json()["tipo"] == "PROFESIONAL"
    assert respuesta.json()["paciente"] is None


def test_yo_sin_token(cliente):
    respuesta = cliente.get("/yo")

    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": "No autenticado"}
    assert respuesta.headers["www-authenticate"] == "Bearer"


def test_yo_token_mal_formado(cliente):
    respuesta = cliente.get("/yo", headers={"Authorization": "Bearer esto-no-es-un-jwt"})

    assert respuesta.status_code == 401


def test_yo_token_vencido(cliente):
    cliente.post("/registro/paciente", json=datos_paciente())
    hace_dos_horas = datetime.now(UTC) - timedelta(hours=2)
    token = tokens.emitir_token("ana.perez@ejemplo.com", "PACIENTE", ahora=hace_dos_horas)

    respuesta = cliente.get("/yo", headers={"Authorization": f"Bearer {token}"})

    assert respuesta.status_code == 401


def test_yo_token_firmado_con_otra_clave(cliente):
    cliente.post("/registro/paciente", json=datos_paciente())
    otra_privada, _ = generar_par_claves()
    ahora = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "ana.perez@ejemplo.com",
            "tipo": "PACIENTE",
            "iss": "usuarios",
            "iat": ahora,
            "exp": ahora + timedelta(minutes=5),
        },
        otra_privada,
        algorithm="RS256",
    )

    respuesta = cliente.get("/yo", headers={"Authorization": f"Bearer {token}"})

    assert respuesta.status_code == 401


def test_yo_token_sin_tipo(cliente, rutas_claves):
    cliente.post("/registro/paciente", json=datos_paciente())
    with open(rutas_claves[0]) as archivo:
        privada = archivo.read()
    ahora = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "ana.perez@ejemplo.com",
            "iss": "usuarios",
            "iat": ahora,
            "exp": ahora + timedelta(minutes=5),
        },
        privada,
        algorithm="RS256",
    )

    respuesta = cliente.get("/yo", headers={"Authorization": f"Bearer {token}"})

    assert respuesta.status_code == 401


def test_yo_usuario_borrado(cliente, fabrica_sesiones):
    cliente.post("/registro/paciente", json=datos_paciente())
    encabezados = iniciar_sesion(cliente, "ana.perez@ejemplo.com")
    with fabrica_sesiones() as sesion:
        sesion.delete(sesion.get(Usuario, "ana.perez@ejemplo.com"))
        sesion.commit()

    respuesta = cliente.get("/yo", headers=encabezados)

    assert respuesta.status_code == 401
