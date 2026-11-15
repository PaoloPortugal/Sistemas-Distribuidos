"""Logs de negocio de Reservas y del publicador (docs/08-observabilidad.md).

Cada línea lleva el correlation_id del pedido y los ids del turno, nunca los
emails de paciente ni profesional.
"""

import asyncio
import datetime
import json
import uuid

from app.db.modelos import EventoSaliente
from app.dominio.publicacion import publicar_pendientes
from tests.conftest import ANA, FRANJA, GOMEZ, SERVICIO, reserva
from tests.test_publicador import INICIO, PUBLICADO, BrokerQueAnotaElContexto

ID_PEDIDO = "pedido-123"


def de_turnos(lineas: list[dict]) -> list[dict]:
    return [linea for linea in lineas if linea["logger"] == "app.dominio.turnos"]


def sin_emails(linea: dict) -> bool:
    texto = json.dumps(linea, ensure_ascii=False)
    return ANA not in texto and GOMEZ not in texto


def test_reservar_registra_el_turno_con_el_correlation_id(cliente, como_ana, lineas_json):
    respuesta = cliente.post(
        "/turnos", json=reserva(), headers=como_ana | {"X-Correlation-ID": ID_PEDIDO}
    )

    id_turno = respuesta.json()["id_turno"]
    (linea,) = de_turnos(lineas_json)
    assert linea["nivel"] == "INFO"
    assert linea["mensaje"] == f"Turno {id_turno} reservado"
    assert linea["correlation_id"] == ID_PEDIDO
    assert (linea["id_turno"], linea["id_disponibilidad"], linea["id_servicio"]) == (
        id_turno,
        FRANJA,
        SERVICIO,
    )
    assert sin_emails(linea)


def test_cancelar_registra_quien_cancelo(cliente, como_ana, lineas_json):
    id_turno = cliente.post("/turnos", json=reserva(), headers=como_ana).json()["id_turno"]
    lineas_json.clear()

    cliente.post(
        f"/turnos/{id_turno}/cancelar",
        json={"motivo": "Viaje"},
        headers=como_ana | {"X-Correlation-ID": ID_PEDIDO},
    )

    (linea,) = de_turnos(lineas_json)
    assert linea["nivel"] == "INFO"
    assert linea["mensaje"] == f"Turno {id_turno} cancelado por el paciente"
    assert linea["correlation_id"] == ID_PEDIDO
    assert (linea["id_turno"], linea["cancelado_por"]) == (id_turno, "PACIENTE")
    assert sin_emails(linea)


def test_horario_ya_reservado_queda_como_advertencia(cliente, como_ana, como_beto, lineas_json):
    cliente.post("/turnos", json=reserva(), headers=como_ana)
    lineas_json.clear()

    cliente.post("/turnos", json=reserva(), headers=como_beto | {"X-Correlation-ID": ID_PEDIDO})

    (linea,) = de_turnos(lineas_json)
    assert linea["nivel"] == "WARNING"
    assert (linea["motivo"], linea["id_disponibilidad"]) == ("HORARIO_YA_RESERVADO", FRANJA)
    assert linea["correlation_id"] == ID_PEDIDO


def test_franja_bloqueada_queda_como_advertencia(cliente, como_ana, lineas_json):
    cliente.put(f"/interno/bloqueos/{FRANJA}")

    cliente.post("/turnos", json=reserva(), headers=como_ana)

    (linea,) = de_turnos(lineas_json)
    assert linea["nivel"] == "WARNING"
    assert (linea["motivo"], linea["id_disponibilidad"]) == ("FRANJA_BLOQUEADA", FRANJA)


def test_catalogo_caido_queda_como_advertencia(cliente, como_ana, catalogo, lineas_json):
    catalogo.caido = True

    cliente.post("/turnos", json=reserva(), headers=como_ana)

    (linea,) = de_turnos(lineas_json)
    assert linea["nivel"] == "WARNING"
    assert (linea["motivo"], linea["id_disponibilidad"]) == ("CATALOGO_NO_DISPONIBLE", FRANJA)


def test_el_publicador_registra_cada_evento_con_su_correlation_id(fabrica_sesiones, lineas_json):
    id_evento = uuid.uuid4()
    with fabrica_sesiones() as sesion:
        sesion.add(
            EventoSaliente(
                id_evento=id_evento,
                tipo="turno.confirmado",
                payload={"id_turno": 15, "correlation_id": "reserva-1"},
                creado_en=INICIO + datetime.timedelta(seconds=1),
            )
        )
        sesion.commit()

    broker = BrokerQueAnotaElContexto()
    asyncio.run(publicar_pendientes(fabrica_sesiones, broker, lote=50, ahora=lambda: PUBLICADO))

    (linea,) = [x for x in lineas_json if x["logger"] == "app.dominio.publicacion"]
    assert linea["nivel"] == "INFO"
    assert linea["mensaje"] == f"Evento turno.confirmado {id_evento} publicado"
    assert linea["correlation_id"] == "reserva-1"
    assert (linea["id_evento"], linea["tipo_evento"], linea["id_turno"]) == (
        str(id_evento),
        "turno.confirmado",
        15,
    )
