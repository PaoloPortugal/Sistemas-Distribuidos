"""Endpoints públicos de médicos: especialidades, servicios y profesionales."""

import datetime

import pytest

from tests.conftest import generar_par_claves

RUTAS_PUBLICAS = [
    "/especialidades",
    "/especialidades/1/servicios",
    "/profesionales",
    "/profesionales/dr.gomez%40ejemplo.com/disponibilidades",
]


# --- Autenticación (común a todos los endpoints públicos) ---


@pytest.mark.parametrize("ruta", RUTAS_PUBLICAS)
def test_sin_token_responde_401(cliente, profesionales, ruta):
    respuesta = cliente.get(ruta)

    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": "No autenticado"}
    assert respuesta.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("ruta", RUTAS_PUBLICAS)
def test_token_mal_formado_responde_401(cliente, profesionales, ruta):
    respuesta = cliente.get(ruta, headers={"Authorization": "Bearer no-es-un-jwt"})

    assert respuesta.status_code == 401


def test_token_vencido_responde_401(cliente, emitir):
    hace_dos_horas = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=2)
    encabezados = emitir(
        "ana@ejemplo.com",
        "PACIENTE",
        iat=hace_dos_horas,
        exp=hace_dos_horas + datetime.timedelta(minutes=60),
    )

    assert cliente.get("/especialidades", headers=encabezados).status_code == 401


def test_token_firmado_con_otra_clave_responde_401(cliente, emitir):
    otra_privada, _ = generar_par_claves()
    encabezados = emitir("ana@ejemplo.com", "PACIENTE", clave=otra_privada)

    assert cliente.get("/especialidades", headers=encabezados).status_code == 401


def test_token_de_otro_emisor_responde_401(cliente, emitir):
    encabezados = emitir("ana@ejemplo.com", "PACIENTE", iss="otro-servicio")

    assert cliente.get("/especialidades", headers=encabezados).status_code == 401


@pytest.mark.parametrize("tipo", ["PACIENTE", "PROFESIONAL"])
def test_cualquier_usuario_autenticado_puede_consultar(cliente, emitir, profesionales, tipo):
    encabezados = emitir("alguien@ejemplo.com", tipo)

    for ruta in RUTAS_PUBLICAS:
        assert cliente.get(ruta, headers=encabezados).status_code == 200, ruta


# --- GET /especialidades ---


def test_listar_especialidades(cliente, emitir):
    respuesta = cliente.get("/especialidades", headers=emitir("ana@ejemplo.com", "PACIENTE"))

    assert respuesta.status_code == 200
    assert {e["id_especialidad"]: e["nombre"] for e in respuesta.json()} == {
        1: "Clínica médica",
        2: "Pediatría",
        3: "Dermatología",
    }
    assert {"id_especialidad": 1, "nombre": "Clínica médica", "descripcion": "Adultos"} in (
        respuesta.json()
    )


# --- GET /especialidades/{id}/servicios ---


def test_listar_servicios_de_una_especialidad(cliente, emitir):
    respuesta = cliente.get(
        "/especialidades/1/servicios", headers=emitir("ana@ejemplo.com", "PACIENTE")
    )

    assert respuesta.status_code == 200
    assert [s["nombre"] for s in respuesta.json()] == ["Consulta general", "Control preventivo"]
    assert all(s["id_especialidad"] == 1 for s in respuesta.json())


def test_especialidad_sin_servicios_devuelve_lista_vacia(cliente, emitir):
    respuesta = cliente.get(
        "/especialidades/3/servicios", headers=emitir("ana@ejemplo.com", "PACIENTE")
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == []


def test_servicios_de_especialidad_inexistente_responde_404(cliente, emitir):
    respuesta = cliente.get(
        "/especialidades/999/servicios", headers=emitir("ana@ejemplo.com", "PACIENTE")
    )

    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "La especialidad no existe"}


# --- GET /profesionales ---


def test_listar_profesionales_con_nombre_y_especialidad(cliente, emitir, profesionales):
    respuesta = cliente.get("/profesionales", headers=emitir("ana@ejemplo.com", "PACIENTE"))

    assert respuesta.status_code == 200
    por_email = {p["email"]: p for p in respuesta.json()}
    assert set(por_email) == {
        "dr.gomez@ejemplo.com",
        "dra.alvarez@ejemplo.com",
        "dra.suarez@ejemplo.com",
    }
    assert por_email["dr.gomez@ejemplo.com"] == {
        "email": "dr.gomez@ejemplo.com",
        "nombre": "Bruno",
        "apellido": "Gómez",
        "matricula": "MP-1",
        "id_especialidad": 1,
        "especialidad": "Clínica médica",
    }


def test_filtrar_profesionales_por_especialidad(cliente, emitir, profesionales):
    respuesta = cliente.get(
        "/profesionales?id_especialidad=2", headers=emitir("ana@ejemplo.com", "PACIENTE")
    )

    assert respuesta.status_code == 200
    assert [p["email"] for p in respuesta.json()] == ["dra.suarez@ejemplo.com"]


def test_especialidad_sin_profesionales_devuelve_lista_vacia(cliente, emitir, profesionales):
    respuesta = cliente.get(
        "/profesionales?id_especialidad=3", headers=emitir("ana@ejemplo.com", "PACIENTE")
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == []


def test_filtrar_por_especialidad_inexistente_responde_404(cliente, emitir):
    respuesta = cliente.get(
        "/profesionales?id_especialidad=999", headers=emitir("ana@ejemplo.com", "PACIENTE")
    )

    assert respuesta.status_code == 404


def test_filtro_no_numerico_responde_422(cliente, emitir):
    respuesta = cliente.get(
        "/profesionales?id_especialidad=cardio", headers=emitir("ana@ejemplo.com", "PACIENTE")
    )

    assert respuesta.status_code == 422
