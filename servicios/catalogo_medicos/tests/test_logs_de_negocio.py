"""Logs de negocio de Catálogo (docs/08-observabilidad.md). Reloj fijo: lunes 2/11/2026 10:00."""

import json

import pytest

from tests.test_disponibilidad import GOMEZ, franja

ID_PEDIDO = "pedido-123"
CON_ID = {"X-Correlation-ID": ID_PEDIDO}


@pytest.fixture
def como_gomez(emitir, profesionales) -> dict:
    return emitir(GOMEZ, "PROFESIONAL")


@pytest.fixture
def id_franja(cliente, como_gomez) -> int:
    respuesta = cliente.post("/disponibilidades", json=franja(), headers=como_gomez)
    return respuesta.json()["id_disponibilidad"]


def de_disponibilidades(lineas: list[dict]) -> list[dict]:
    return [linea for linea in lineas if linea["logger"] == "app.dominio.disponibilidades"]


def test_crear_disponibilidad(cliente, como_gomez, lineas_json):
    respuesta = cliente.post("/disponibilidades", json=franja(), headers=como_gomez | CON_ID)

    id_disponibilidad = respuesta.json()["id_disponibilidad"]
    (linea,) = de_disponibilidades(lineas_json)
    assert linea["nivel"] == "INFO"
    assert linea["mensaje"] == f"Disponibilidad {id_disponibilidad} creada"
    assert linea["correlation_id"] == ID_PEDIDO
    assert (
        linea["id_disponibilidad"],
        linea["fecha_disponibilidad"],
        linea["horario_inicio"],
        linea["horario_fin"],
    ) == (id_disponibilidad, "2026-11-03", "09:00:00", "09:30:00")
    assert GOMEZ not in json.dumps(linea, ensure_ascii=False)


def test_eliminar_disponibilidad(cliente, como_gomez, id_franja, lineas_json):
    lineas_json.clear()

    cliente.delete(f"/disponibilidades/{id_franja}", headers=como_gomez | CON_ID)

    (linea,) = de_disponibilidades(lineas_json)
    assert linea["nivel"] == "INFO"
    assert linea["mensaje"] == f"Disponibilidad {id_franja} eliminada"
    assert (linea["id_disponibilidad"], linea["correlation_id"]) == (id_franja, ID_PEDIDO)


def test_borrado_rechazado_por_un_turno_queda_como_advertencia(
    cliente, como_gomez, id_franja, reservas, lineas_json
):
    reservas.reservadas.add(id_franja)
    lineas_json.clear()

    cliente.delete(f"/disponibilidades/{id_franja}", headers=como_gomez | CON_ID)

    (linea,) = de_disponibilidades(lineas_json)
    assert linea["nivel"] == "WARNING"
    assert (linea["motivo"], linea["id_disponibilidad"]) == ("DISPONIBILIDAD_CON_TURNO", id_franja)
    assert linea["correlation_id"] == ID_PEDIDO
