"""Endpoints internos para catálogo: horarios ocupados y bloqueo al borrar (ADR 003).

El lock entre bloquear y reservar es de PostgreSQL; se prueba contra Docker
en pruebas/concurrencia/test_reservar_vs_borrar.py.
"""

import datetime

from app.db.modelos import DisponibilidadBloqueada, Turno
from tests.conftest import FRANJA, GOMEZ, reserva

OTRA_FRANJA = 8


def ocupadas(cliente, ids: list[int]):
    return cliente.post("/interno/disponibilidades-ocupadas", json={"ids": ids})


def bloqueadas(fabrica_sesiones) -> list[int]:
    with fabrica_sesiones() as sesion:
        return [b.id_disponibilidad for b in sesion.query(DisponibilidadBloqueada)]


# --- POST /interno/disponibilidades-ocupadas ---


def test_ocupadas_vacio(cliente):
    respuesta = ocupadas(cliente, [])

    assert respuesta.status_code == 200
    assert respuesta.json() == {"ocupadas": []}


def test_ocupadas_reservada_bloqueada_y_libre(cliente, catalogo, como_ana):
    catalogo.agregar_franja(OTRA_FRANJA, GOMEZ, datetime.date(2026, 11, 5), "10:00", "10:30")
    assert cliente.post("/turnos", json=reserva(), headers=como_ana).status_code == 201
    assert cliente.put("/interno/bloqueos/9").status_code == 204

    respuesta = ocupadas(cliente, [9, OTRA_FRANJA, FRANJA, 10])

    assert respuesta.json() == {"ocupadas": [FRANJA, 9]}


def test_una_reserva_cancelada_libera_el_horario(cliente, como_ana):
    id_turno = cliente.post("/turnos", json=reserva(), headers=como_ana).json()["id_turno"]
    assert cliente.post(f"/turnos/{id_turno}/cancelar", headers=como_ana).status_code == 200

    assert ocupadas(cliente, [FRANJA]).json() == {"ocupadas": []}


def test_ocupadas_con_mas_de_5000_ids_responde_422(cliente):
    assert ocupadas(cliente, list(range(5001))).status_code == 422


# --- PUT y DELETE /interno/bloqueos/{id} ---


def test_bloquear_un_horario_libre(cliente, fabrica_sesiones):
    respuesta = cliente.put(f"/interno/bloqueos/{FRANJA}")

    assert respuesta.status_code == 204
    assert bloqueadas(fabrica_sesiones) == [FRANJA]


def test_bloquear_dos_veces_es_idempotente(cliente, fabrica_sesiones):
    cliente.put(f"/interno/bloqueos/{FRANJA}")

    assert cliente.put(f"/interno/bloqueos/{FRANJA}").status_code == 204
    assert bloqueadas(fabrica_sesiones) == [FRANJA]


def test_bloquear_un_horario_con_turno_responde_409(cliente, como_ana, fabrica_sesiones):
    cliente.post("/turnos", json=reserva(), headers=como_ana)

    respuesta = cliente.put(f"/interno/bloqueos/{FRANJA}")

    assert respuesta.status_code == 409
    assert respuesta.json() == {
        "detail": "El horario tiene un turno reservado",
        "codigo": "DISPONIBILIDAD_CON_TURNO",
    }
    assert bloqueadas(fabrica_sesiones) == []


def test_bloquear_un_horario_con_turno_cancelado(cliente, como_ana, fabrica_sesiones):
    id_turno = cliente.post("/turnos", json=reserva(), headers=como_ana).json()["id_turno"]
    cliente.post(f"/turnos/{id_turno}/cancelar", headers=como_ana)

    assert cliente.put(f"/interno/bloqueos/{FRANJA}").status_code == 204
    # El turno cancelado conserva su copia de la franja (ADR 006).
    with fabrica_sesiones() as sesion:
        assert sesion.get(Turno, id_turno).horario_inicio == datetime.time(9, 0)


def test_desbloquear(cliente, fabrica_sesiones):
    cliente.put(f"/interno/bloqueos/{FRANJA}")

    assert cliente.delete(f"/interno/bloqueos/{FRANJA}").status_code == 204
    assert bloqueadas(fabrica_sesiones) == []
    # Idempotente: desbloquear algo que no está bloqueado también da 204.
    assert cliente.delete(f"/interno/bloqueos/{FRANJA}").status_code == 204


# --- POST /turnos sobre un horario bloqueado ---


def test_reservar_un_horario_bloqueado_responde_409(cliente, como_ana, fabrica_sesiones):
    cliente.put(f"/interno/bloqueos/{FRANJA}")

    respuesta = cliente.post("/turnos", json=reserva(), headers=como_ana)

    assert respuesta.status_code == 409
    assert respuesta.json() == {"detail": "El horario no está disponible en este momento"}
    with fabrica_sesiones() as sesion:
        assert sesion.query(Turno).count() == 0


def test_despues_de_desbloquear_se_puede_reservar(cliente, como_ana):
    cliente.put(f"/interno/bloqueos/{FRANJA}")
    cliente.delete(f"/interno/bloqueos/{FRANJA}")

    assert cliente.post("/turnos", json=reserva(), headers=como_ana).status_code == 201
