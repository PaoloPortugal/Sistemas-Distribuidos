"""Horarios libres en los listados y borrado de franjas (ADR 003).

Reservas está reemplazado por ReservasFalso. Reloj fijo: lunes 2/11/2026 10:00.
"""

import datetime

import pytest

from app.clientes.reservas import ReservasNoDisponible, obtener_cliente_reservas
from app.db.modelos import Disponibilidad
from app.main import app
from tests.test_disponibilidad import GOMEZ, franja, franjas_en_base

LISTADO_PUBLICO = "/profesionales/dr.gomez%40ejemplo.com/disponibilidades"


@pytest.fixture
def como_gomez(emitir, profesionales) -> dict:
    return emitir(GOMEZ, "PROFESIONAL")


@pytest.fixture
def como_paciente(emitir) -> dict:
    return emitir("ana.perez@ejemplo.com", "PACIENTE")


@pytest.fixture
def ids(cliente, como_gomez) -> dict[str, int]:
    """Dos franjas futuras de Gómez, mañana a las 9:00 y a las 10:00."""
    creadas = {}
    for nombre, inicio, fin in [("manana_9", "09:00", "09:30"), ("manana_10", "10:00", "10:30")]:
        respuesta = cliente.post(
            "/disponibilidades", json=franja("2026-11-03", inicio, fin), headers=como_gomez
        )
        creadas[nombre] = respuesta.json()["id_disponibilidad"]
    return creadas


@pytest.fixture
def franja_de_hoy_que_ya_paso(fabrica_sesiones, profesionales) -> int:
    """Se inserta directo: la API no deja crear franjas en el pasado."""
    with fabrica_sesiones() as sesion:
        d = Disponibilidad(
            email_profesional=GOMEZ,
            fecha=datetime.date(2026, 11, 2),
            horario_inicio=datetime.time(9, 0),
            horario_fin=datetime.time(9, 30),
        )
        sesion.add(d)
        sesion.commit()
        return d.id_disponibilidad


def libres(respuesta) -> list[tuple[str, bool | None]]:
    return [(d["horario_inicio"], d["libre"]) for d in respuesta.json()]


# --- Listados con `libre` ---


def test_listado_marca_libres_y_ocupadas(cliente, como_paciente, ids, reservas):
    reservas.reservadas.add(ids["manana_9"])

    respuesta = cliente.get(LISTADO_PUBLICO, headers=como_paciente)

    assert respuesta.status_code == 200
    assert libres(respuesta) == [("09:00:00", False), ("10:00:00", True)]
    assert set(respuesta.json()[0]) == {
        "id_disponibilidad", "email_profesional", "fecha", "horario_inicio", "horario_fin", "libre"
    }


def test_una_franja_bloqueada_no_esta_libre(cliente, como_paciente, ids, reservas):
    reservas.bloqueadas.add(ids["manana_10"])

    respuesta = cliente.get(LISTADO_PUBLICO, headers=como_paciente)

    assert libres(respuesta) == [("09:00:00", True), ("10:00:00", False)]


def test_una_franja_que_ya_empezo_no_esta_libre_y_no_se_consulta(
    cliente, como_paciente, ids, franja_de_hoy_que_ya_paso, reservas
):
    respuesta = cliente.get(LISTADO_PUBLICO, headers=como_paciente)

    assert [(d["fecha"], d["libre"]) for d in respuesta.json()] == [
        ("2026-11-02", False),
        ("2026-11-03", True),
        ("2026-11-03", True),
    ]
    assert reservas.consultas == [[ids["manana_9"], ids["manana_10"]]]


def test_solo_libres(cliente, como_paciente, ids, franja_de_hoy_que_ya_paso, reservas):
    reservas.reservadas.add(ids["manana_9"])

    respuesta = cliente.get(f"{LISTADO_PUBLICO}?solo_libres=true", headers=como_paciente)

    assert respuesta.status_code == 200
    assert [d["id_disponibilidad"] for d in respuesta.json()] == [ids["manana_10"]]


def test_mis_disponibilidades_tambien_marca_y_filtra(cliente, como_gomez, ids, reservas):
    reservas.reservadas.add(ids["manana_10"])

    todas = cliente.get("/mis-disponibilidades", headers=como_gomez)
    solo = cliente.get("/mis-disponibilidades?solo_libres=true", headers=como_gomez)

    assert libres(todas) == [("09:00:00", True), ("10:00:00", False)]
    assert [d["id_disponibilidad"] for d in solo.json()] == [ids["manana_9"]]


def test_reservas_caido_el_listado_sale_sin_marcar(
    cliente, como_paciente, ids, franja_de_hoy_que_ya_paso, reservas
):
    reservas.caido = True

    respuesta = cliente.get(LISTADO_PUBLICO, headers=como_paciente)

    assert respuesta.status_code == 200
    # La que ya empezó se sabe que no está libre; las futuras, no se sabe.
    assert [d["libre"] for d in respuesta.json()] == [False, None, None]


@pytest.mark.parametrize(
    "ruta", [f"{LISTADO_PUBLICO}?solo_libres=true", "/mis-disponibilidades?solo_libres=true"]
)
def test_reservas_caido_con_solo_libres_responde_503(cliente, emitir, ids, reservas, ruta):
    reservas.caido = True

    respuesta = cliente.get(ruta, headers=emitir(GOMEZ, "PROFESIONAL"))

    assert respuesta.status_code == 503
    assert "reservas no está disponible" in respuesta.json()["detail"]


def test_sin_franjas_no_consulta_a_reservas(cliente, como_paciente, profesionales, reservas):
    reservas.caido = True

    respuesta = cliente.get(f"{LISTADO_PUBLICO}?solo_libres=true", headers=como_paciente)

    assert respuesta.status_code == 200
    assert respuesta.json() == []
    assert reservas.consultas == []


# --- DELETE /disponibilidades/{id} ---


def test_borrar_una_franja_libre(cliente, como_gomez, ids, fabrica_sesiones, reservas):
    respuesta = cliente.delete(f"/disponibilidades/{ids['manana_9']}", headers=como_gomez)

    assert respuesta.status_code == 204
    assert franjas_en_base(fabrica_sesiones) == [(GOMEZ, "2026-11-03", "10:00")]
    # El bloqueo de la franja borrada queda en reservas.
    assert reservas.bloqueadas == {ids["manana_9"]}


def test_despues_de_borrar_se_puede_crear_otra_en_el_mismo_horario(cliente, como_gomez, ids):
    cliente.delete(f"/disponibilidades/{ids['manana_9']}", headers=como_gomez)

    respuesta = cliente.post("/disponibilidades", json=franja(), headers=como_gomez)

    assert respuesta.status_code == 201
    assert respuesta.json()["id_disponibilidad"] != ids["manana_9"]


def test_borrar_una_franja_con_turno_responde_409(
    cliente, como_gomez, ids, fabrica_sesiones, reservas
):
    reservas.reservadas.add(ids["manana_9"])

    respuesta = cliente.delete(f"/disponibilidades/{ids['manana_9']}", headers=como_gomez)

    assert respuesta.status_code == 409
    assert "turno reservado" in respuesta.json()["detail"]
    assert len(franjas_en_base(fabrica_sesiones)) == 2
    assert reservas.bloqueadas == set()


def test_borrar_una_franja_ajena_responde_403(cliente, emitir, ids, fabrica_sesiones, reservas):
    respuesta = cliente.delete(
        f"/disponibilidades/{ids['manana_9']}", headers=emitir("dra.alvarez@ejemplo.com", "PROFESIONAL")
    )

    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": "La franja no es tuya"}
    assert len(franjas_en_base(fabrica_sesiones)) == 2
    assert reservas.bloqueadas == set()


def test_un_paciente_no_puede_borrar_responde_403(cliente, como_paciente, ids, fabrica_sesiones):
    respuesta = cliente.delete(f"/disponibilidades/{ids['manana_9']}", headers=como_paciente)

    assert respuesta.status_code == 403
    assert len(franjas_en_base(fabrica_sesiones)) == 2


def test_borrar_sin_token_responde_401(cliente, ids):
    assert cliente.delete(f"/disponibilidades/{ids['manana_9']}").status_code == 401


def test_borrar_una_franja_inexistente_responde_404(cliente, como_gomez, ids):
    respuesta = cliente.delete("/disponibilidades/9999", headers=como_gomez)

    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "La franja no existe"}


def test_borrar_una_franja_que_ya_empezo_responde_422(
    cliente, como_gomez, franja_de_hoy_que_ya_paso, fabrica_sesiones, reservas
):
    respuesta = cliente.delete(f"/disponibilidades/{franja_de_hoy_que_ya_paso}", headers=como_gomez)

    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": "No se puede borrar una franja que ya empezó"}
    assert len(franjas_en_base(fabrica_sesiones)) == 1
    assert reservas.bloqueadas == set()


def test_reservas_caido_al_borrar_responde_503_y_no_borra(
    cliente, como_gomez, ids, fabrica_sesiones, reservas
):
    reservas.caido = True

    respuesta = cliente.delete(f"/disponibilidades/{ids['manana_9']}", headers=como_gomez)

    assert respuesta.status_code == 503
    assert len(franjas_en_base(fabrica_sesiones)) == 2


class ReservasQueBloqueaYNoResponde:
    """Bloquea pero la respuesta no llega (timeout de lectura): hay que compensar."""

    def __init__(self, reservas):
        self._reservas = reservas

    def ocupadas(self, ids):
        return self._reservas.ocupadas(ids)

    def bloquear(self, id_disponibilidad):
        self._reservas.bloquear(id_disponibilidad)
        raise ReservasNoDisponible("read timeout")

    def desbloquear(self, id_disponibilidad):
        self._reservas.desbloquear(id_disponibilidad)


def test_si_el_bloqueo_pudo_aplicarse_se_compensa(
    cliente, como_gomez, ids, fabrica_sesiones, reservas
):
    app.dependency_overrides[obtener_cliente_reservas] = lambda: ReservasQueBloqueaYNoResponde(
        reservas
    )

    respuesta = cliente.delete(f"/disponibilidades/{ids['manana_9']}", headers=como_gomez)

    assert respuesta.status_code == 503
    assert len(franjas_en_base(fabrica_sesiones)) == 2
    assert reservas.bloqueadas == set()


def test_borrar_dos_veces_la_segunda_responde_404(cliente, como_gomez, ids):
    assert cliente.delete(f"/disponibilidades/{ids['manana_9']}", headers=como_gomez).status_code == 204

    respuesta = cliente.delete(f"/disponibilidades/{ids['manana_9']}", headers=como_gomez)

    assert respuesta.status_code == 404
