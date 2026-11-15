"""Logs de negocio de Usuarios (docs/08-observabilidad.md).

Las líneas nuevas identifican el tipo de usuario, nunca el email ni la contraseña.
"""

import json

from app.clientes.catalogo import CatalogoNoDisponible
from tests.conftest import CONTRASENA, datos_paciente, datos_profesional
from tests.test_registro_profesional import commit_falla  # noqa: F401 (fixture)

ID_PEDIDO = "pedido-123"
CON_ID = {"X-Correlation-ID": ID_PEDIDO}


def de_usuarios(lineas: list[dict]) -> list[dict]:
    return [linea for linea in lineas if linea["logger"] == "app.dominio.usuarios"]


def sin_datos_personales(linea: dict, email: str) -> bool:
    texto = json.dumps(linea, ensure_ascii=False)
    return email not in texto and CONTRASENA not in texto


def test_registro_de_paciente(cliente, lineas_json):
    cliente.post("/registro/paciente", json=datos_paciente(), headers=CON_ID)

    (linea,) = de_usuarios(lineas_json)
    assert linea["nivel"] == "INFO"
    assert linea["mensaje"] == "Paciente registrado"
    assert linea["tipo_usuario"] == "PACIENTE"
    assert linea["correlation_id"] == ID_PEDIDO
    assert sin_datos_personales(linea, "ana.perez@ejemplo.com")


def test_registro_de_profesional(cliente, catalogo, lineas_json):
    cliente.post("/registro/profesional", json=datos_profesional(), headers=CON_ID)

    (linea,) = de_usuarios(lineas_json)
    assert linea["nivel"] == "INFO"
    assert linea["mensaje"] == "Profesional registrado"
    assert (linea["tipo_usuario"], linea["id_especialidad"]) == ("PROFESIONAL", 1)
    assert linea["correlation_id"] == ID_PEDIDO
    assert sin_datos_personales(linea, "dr.gomez@ejemplo.com")


def test_catalogo_caido_queda_como_advertencia(cliente, catalogo, lineas_json):
    catalogo.error_al_crear = CatalogoNoDisponible("timeout de lectura", puede_haber_creado=True)

    cliente.post("/registro/profesional", json=datos_profesional(), headers=CON_ID)

    (linea,) = de_usuarios(lineas_json)
    assert linea["nivel"] == "WARNING"
    assert linea["compensa"] is True
    assert linea["correlation_id"] == ID_PEDIDO
    assert sin_datos_personales(linea, "dr.gomez@ejemplo.com")


def test_falla_el_commit_queda_como_advertencia_sin_los_parametros_sql(
    cliente, catalogo, commit_falla, lineas_json  # noqa: F811
):
    cliente.post("/registro/profesional", json=datos_profesional(), headers=CON_ID)

    (linea,) = [x for x in de_usuarios(lineas_json) if x["nivel"] == "WARNING"]
    assert linea["mensaje"] == (
        "Alta de profesional no completada: no se pudo confirmar el usuario (OperationalError)"
    )
    assert linea["compensa"] is True
    assert linea["correlation_id"] == ID_PEDIDO
    assert sin_datos_personales(linea, "dr.gomez@ejemplo.com")
