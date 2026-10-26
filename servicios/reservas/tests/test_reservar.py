"""POST /turnos, GET /mis-turnos y GET /agenda. Reloj fijo: lunes 2/11/2026 10:00."""

import datetime

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.modelos import EventoSaliente, Turno
from app.db.sesion import obtener_sesion
from app.main import app
from tests.conftest import (
    ALVAREZ,
    ANA,
    BETO,
    FRANJA,
    GOMEZ,
    SERVICIO,
    SERVICIO_DE_OTRA_ESPECIALIDAD,
    generar_par_claves,
    reserva,
)


def turnos_y_eventos(fabrica_sesiones) -> tuple[list[Turno], list[EventoSaliente]]:
    with fabrica_sesiones() as sesion:
        return (
            list(sesion.query(Turno).order_by(Turno.id_turno)),
            list(sesion.query(EventoSaliente).order_by(EventoSaliente.creado_en)),
        )


# --- POST /turnos ---


def test_reservar_crea_el_turno_y_el_evento(cliente, como_ana, fabrica_sesiones):
    respuesta = cliente.post("/turnos", json=reserva(), headers=como_ana)

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo | {"id_turno": 0, "fecha_creacion": ""} == {
        "id_turno": 0,
        "estado": "RESERVADO",
        "email_paciente": ANA,
        "email_profesional": GOMEZ,
        "id_disponibilidad": FRANJA,
        "id_servicio": SERVICIO,
        "fecha": "2026-11-05",
        "horario_inicio": "09:00:00",
        "horario_fin": "09:30:00",
        "fecha_creacion": "",
        "fecha_cancelacion": None,
        "motivo_cancelacion": None,
        "cancelado_por": None,
    }
    turnos, eventos = turnos_y_eventos(fabrica_sesiones)
    assert len(turnos) == 1
    assert [e.tipo for e in eventos] == ["turno.confirmado"]
    payload = eventos[0].payload
    assert payload["id_evento"] == str(eventos[0].id_evento)
    assert payload | {"id_evento": "", "ocurrido_en": ""} == {
        "id_evento": "",
        "tipo": "turno.confirmado",
        "ocurrido_en": "",
        "id_turno": cuerpo["id_turno"],
        "id_disponibilidad": FRANJA,
        "id_servicio": SERVICIO,
        "email_paciente": ANA,
        "email_profesional": GOMEZ,
        "fecha": "2026-11-05",
        "horario_inicio": "09:00:00",
        "horario_fin": "09:30:00",
    }
    assert eventos[0].publicado_en is None


def test_el_paciente_sale_del_token(cliente, emitir, fabrica_sesiones):
    datos = reserva() | {"email_paciente": "otro@ejemplo.com"}

    respuesta = cliente.post(
        "/turnos", json=datos, headers=emitir("Ana.Perez@Ejemplo.com", "PACIENTE")
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["email_paciente"] == ANA


def test_reservar_sin_token_responde_401(cliente, catalogo):
    respuesta = cliente.post("/turnos", json=reserva())

    assert respuesta.status_code == 401
    assert catalogo.consultas == 0


def test_reservar_con_token_de_otra_clave_responde_401(cliente, emitir):
    otra, _ = generar_par_claves()

    respuesta = cliente.post("/turnos", json=reserva(), headers=emitir(ANA, "PACIENTE", clave=otra))

    assert respuesta.status_code == 401


def test_profesional_no_puede_reservar_responde_403(cliente, como_gomez, catalogo):
    respuesta = cliente.post("/turnos", json=reserva(), headers=como_gomez)

    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": "Solo para pacientes"}
    assert catalogo.consultas == 0


def test_disponibilidad_inexistente_responde_404(cliente, como_ana, fabrica_sesiones):
    respuesta = cliente.post("/turnos", json=reserva(id_disponibilidad=999), headers=como_ana)

    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "La disponibilidad no existe"}
    assert turnos_y_eventos(fabrica_sesiones) == ([], [])


def test_servicio_inexistente_responde_404(cliente, como_ana, fabrica_sesiones):
    respuesta = cliente.post("/turnos", json=reserva(id_servicio=999), headers=como_ana)

    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "El servicio no existe"}
    assert turnos_y_eventos(fabrica_sesiones) == ([], [])


def test_servicio_de_otra_especialidad_responde_422(cliente, como_ana, fabrica_sesiones):
    respuesta = cliente.post(
        "/turnos", json=reserva(id_servicio=SERVICIO_DE_OTRA_ESPECIALIDAD), headers=como_ana
    )

    assert respuesta.status_code == 422
    assert respuesta.json() == {
        "detail": "El servicio no corresponde a la especialidad del profesional"
    }
    assert turnos_y_eventos(fabrica_sesiones) == ([], [])


@pytest.mark.parametrize(
    ("fecha", "inicio"),
    [(datetime.date(2026, 11, 1), "15:00"), (datetime.date(2026, 11, 2), "10:00")],
    ids=["ayer", "empieza-justo-ahora"],
)
def test_franja_en_el_pasado_responde_422(cliente, como_ana, catalogo, fabrica_sesiones, fecha, inicio):
    catalogo.agregar_franja(20, GOMEZ, fecha, inicio, "23:00")

    respuesta = cliente.post("/turnos", json=reserva(id_disponibilidad=20), headers=como_ana)

    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": "La franja ya pasó"}
    assert turnos_y_eventos(fabrica_sesiones) == ([], [])


def test_horario_ya_reservado_responde_409(cliente, como_ana, como_beto, fabrica_sesiones):
    assert cliente.post("/turnos", json=reserva(), headers=como_ana).status_code == 201

    respuesta = cliente.post("/turnos", json=reserva(), headers=como_beto)

    assert respuesta.status_code == 409
    assert respuesta.json() == {"detail": "El horario ya está reservado"}
    turnos, eventos = turnos_y_eventos(fabrica_sesiones)
    assert [(t.email_paciente, t.estado) for t in turnos] == [(ANA, "RESERVADO")]
    assert len(eventos) == 1  # el intento rechazado no deja evento


def test_el_mismo_paciente_no_puede_reservar_dos_veces(cliente, como_ana):
    cliente.post("/turnos", json=reserva(), headers=como_ana)

    assert cliente.post("/turnos", json=reserva(), headers=como_ana).status_code == 409


def test_catalogo_no_disponible_responde_503_sin_crear_nada(
    cliente, como_ana, catalogo, fabrica_sesiones
):
    catalogo.caido = True

    respuesta = cliente.post("/turnos", json=reserva(), headers=como_ana)

    assert respuesta.status_code == 503
    assert respuesta.json() == {"detail": "El catálogo no está disponible. Intentá de nuevo más tarde"}
    assert turnos_y_eventos(fabrica_sesiones) == ([], [])


@pytest.mark.parametrize(
    "datos",
    [{"id_disponibilidad": 7}, {"id_disponibilidad": 0, "id_servicio": 1}, {"id_disponibilidad": "x", "id_servicio": 1}],
    ids=["falta-servicio", "id-cero", "id-no-numerico"],
)
def test_cuerpo_invalido_responde_422(cliente, como_ana, catalogo, datos):
    assert cliente.post("/turnos", json=datos, headers=como_ana).status_code == 422
    assert catalogo.consultas == 0


class SesionQueFallaAlConfirmar(Session):
    def commit(self):
        raise OperationalError("COMMIT", {}, Exception("se perdió la conexión"))


def test_turno_y_evento_van_en_la_misma_transaccion(como_ana, catalogo, reloj_fijo, motor, fabrica_sesiones):
    """Si el commit falla no queda ni el turno ni el evento (ADR 005)."""
    from fastapi.testclient import TestClient

    from app.clientes.catalogo import obtener_cliente_catalogo
    from app.dominio import reloj

    def sesion_que_falla():
        with SesionQueFallaAlConfirmar(bind=motor, autoflush=False) as sesion:
            yield sesion

    app.dependency_overrides[obtener_sesion] = sesion_que_falla
    app.dependency_overrides[obtener_cliente_catalogo] = lambda: catalogo
    app.dependency_overrides[reloj.ahora] = lambda: reloj_fijo.ahora
    try:
        with TestClient(app, raise_server_exceptions=False) as cliente:
            respuesta = cliente.post("/turnos", json=reserva(), headers=como_ana)
    finally:
        app.dependency_overrides.clear()

    assert respuesta.status_code == 500
    assert turnos_y_eventos(fabrica_sesiones) == ([], [])


# --- Reservar, cancelar y volver a reservar ---


def test_reservar_cancelar_y_volver_a_reservar(cliente, como_ana, como_beto, fabrica_sesiones):
    primero = cliente.post("/turnos", json=reserva(), headers=como_ana).json()
    cancelado = cliente.post(f"/turnos/{primero['id_turno']}/cancelar", json={}, headers=como_ana)
    assert cancelado.status_code == 200

    respuesta = cliente.post("/turnos", json=reserva(), headers=como_beto)

    assert respuesta.status_code == 201
    turnos, eventos = turnos_y_eventos(fabrica_sesiones)
    assert [(t.email_paciente, t.estado) for t in turnos] == [(ANA, "CANCELADO"), (BETO, "RESERVADO")]
    assert [e.tipo for e in eventos] == ["turno.confirmado", "turno.cancelado", "turno.confirmado"]


# --- GET /mis-turnos ---


def test_mis_turnos_solo_los_propios(cliente, como_ana, como_beto, catalogo):
    catalogo.agregar_franja(8, GOMEZ, datetime.date(2026, 11, 4), "11:00", "11:30")
    cliente.post("/turnos", json=reserva(), headers=como_ana)
    cliente.post("/turnos", json=reserva(id_disponibilidad=8), headers=como_beto)

    respuesta = cliente.get("/mis-turnos", headers=como_ana)

    assert respuesta.status_code == 200
    assert [(t["id_disponibilidad"], t["email_paciente"]) for t in respuesta.json()] == [(FRANJA, ANA)]


def test_mis_turnos_incluye_los_cancelados(cliente, como_ana):
    turno = cliente.post("/turnos", json=reserva(), headers=como_ana).json()
    cliente.post(f"/turnos/{turno['id_turno']}/cancelar", json={}, headers=como_ana)

    respuesta = cliente.get("/mis-turnos", headers=como_ana)

    assert [t["estado"] for t in respuesta.json()] == ["CANCELADO"]


def test_mis_turnos_sin_token_responde_401(cliente):
    assert cliente.get("/mis-turnos").status_code == 401


def test_mis_turnos_de_profesional_responde_403(cliente, como_gomez):
    assert cliente.get("/mis-turnos", headers=como_gomez).status_code == 403


# --- GET /agenda ---


@pytest.fixture
def turnos_de_la_semana(cliente, catalogo, como_ana, como_beto):
    catalogo.agregar_franja(8, GOMEZ, datetime.date(2026, 11, 3), "11:00", "11:30")
    catalogo.agregar_franja(9, ALVAREZ, datetime.date(2026, 11, 3), "11:00", "11:30")
    catalogo.agregar_franja(10, GOMEZ, datetime.date(2026, 12, 20), "11:00", "11:30")
    for franja, encabezados in [(FRANJA, como_ana), (8, como_beto), (9, como_ana), (10, como_ana)]:
        assert cliente.post("/turnos", json=reserva(id_disponibilidad=franja), headers=encabezados).status_code == 201


def test_agenda_por_defecto_hoy_y_30_dias(cliente, como_gomez, turnos_de_la_semana):
    respuesta = cliente.get("/agenda", headers=como_gomez)

    assert respuesta.status_code == 200
    assert [(t["fecha"], t["email_paciente"]) for t in respuesta.json()] == [
        ("2026-11-03", BETO),
        ("2026-11-05", ANA),
    ]


def test_agenda_con_rango(cliente, como_gomez, turnos_de_la_semana):
    respuesta = cliente.get("/agenda?desde=2026-11-04&hasta=2026-12-31", headers=como_gomez)

    assert [t["fecha"] for t in respuesta.json()] == ["2026-11-05", "2026-12-20"]


def test_agenda_solo_la_propia(cliente, como_alvarez, turnos_de_la_semana):
    respuesta = cliente.get("/agenda", headers=como_alvarez)

    assert [t["id_disponibilidad"] for t in respuesta.json()] == [9]


def test_agenda_sin_token_responde_401(cliente):
    assert cliente.get("/agenda").status_code == 401


def test_agenda_de_paciente_responde_403(cliente, como_ana):
    respuesta = cliente.get("/agenda", headers=como_ana)

    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": "Solo para profesionales"}


@pytest.mark.parametrize(
    "consulta", ["desde=2026-11-10&hasta=2026-11-01", "desde=2026-11-01&hasta=2027-03-01"]
)
def test_agenda_rango_invalido_responde_422(cliente, como_gomez, consulta):
    assert cliente.get(f"/agenda?{consulta}", headers=como_gomez).status_code == 422
