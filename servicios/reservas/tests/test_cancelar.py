"""POST /turnos/{id}/cancelar y el plazo por quién cancela (ADR 007)."""

import datetime

import pytest

from app.db.modelos import EventoSaliente, Turno
from tests.conftest import AHORA, ANA, GOMEZ, reserva

PLAZO_PACIENTE = "El paciente solo puede cancelar hasta 24 horas antes del turno"
YA_EMPEZO = "El turno ya empezó"


@pytest.fixture
def turno_de_ana(cliente, como_ana) -> int:
    """Turno del jueves 5/11 a las 9:00: faltan casi 3 días."""
    return cliente.post("/turnos", json=reserva(), headers=como_ana).json()["id_turno"]


def turno_que_empieza(cliente, catalogo, como_ana, inicio: datetime.datetime) -> int:
    hora = inicio.strftime("%H:%M")
    catalogo.agregar_franja(50, GOMEZ, inicio.date(), hora, "23:59")
    respuesta = cliente.post("/turnos", json=reserva(id_disponibilidad=50), headers=como_ana)
    assert respuesta.status_code == 201
    return respuesta.json()["id_turno"]


def turno_y_eventos(fabrica_sesiones, id_turno) -> tuple[Turno, list[EventoSaliente]]:
    with fabrica_sesiones() as sesion:
        eventos = sesion.query(EventoSaliente).order_by(EventoSaliente.creado_en).all()
        return sesion.get(Turno, id_turno), eventos


# --- Quién puede cancelar ---


def test_paciente_cancela_su_turno(cliente, como_ana, turno_de_ana, fabrica_sesiones):
    respuesta = cliente.post(
        f"/turnos/{turno_de_ana}/cancelar", json={"motivo": "Viaje"}, headers=como_ana
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert (cuerpo["estado"], cuerpo["cancelado_por"], cuerpo["motivo_cancelacion"]) == (
        "CANCELADO",
        "PACIENTE",
        "Viaje",
    )
    turno, eventos = turno_y_eventos(fabrica_sesiones, turno_de_ana)
    assert turno.estado == "CANCELADO"
    assert [e.tipo for e in eventos] == ["turno.confirmado", "turno.cancelado"]
    assert eventos[1].payload | {"id_evento": "", "ocurrido_en": ""} == {
        "id_evento": "",
        "tipo": "turno.cancelado",
        "ocurrido_en": "",
        "id_turno": turno_de_ana,
        "id_disponibilidad": 7,
        "id_servicio": 1,
        "email_paciente": ANA,
        "email_profesional": GOMEZ,
        "fecha": "2026-11-05",
        "horario_inicio": "09:00:00",
        "horario_fin": "09:30:00",
        "cancelado_por": "PACIENTE",
        "motivo": "Viaje",
    }


def test_profesional_cancela_un_turno_de_su_agenda(cliente, como_gomez, turno_de_ana):
    respuesta = cliente.post(
        f"/turnos/{turno_de_ana}/cancelar", json={"motivo": "Congreso"}, headers=como_gomez
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["cancelado_por"] == "PROFESIONAL"


@pytest.mark.parametrize("cuerpo", [None, {}, {"motivo": None}], ids=["sin-cuerpo", "vacio", "motivo-nulo"])
def test_el_motivo_es_opcional(cliente, como_ana, turno_de_ana, cuerpo):
    respuesta = cliente.post(f"/turnos/{turno_de_ana}/cancelar", json=cuerpo, headers=como_ana)

    assert respuesta.status_code == 200
    assert respuesta.json()["motivo_cancelacion"] is None


def test_motivo_demasiado_largo_responde_422(cliente, como_ana, turno_de_ana):
    respuesta = cliente.post(
        f"/turnos/{turno_de_ana}/cancelar", json={"motivo": "x" * 501}, headers=como_ana
    )

    assert respuesta.status_code == 422


def test_otro_paciente_responde_403(cliente, como_beto, turno_de_ana, fabrica_sesiones):
    respuesta = cliente.post(f"/turnos/{turno_de_ana}/cancelar", json={}, headers=como_beto)

    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": "El turno no es tuyo"}
    assert turno_y_eventos(fabrica_sesiones, turno_de_ana)[0].estado == "RESERVADO"


def test_otro_profesional_responde_403(cliente, como_alvarez, turno_de_ana):
    respuesta = cliente.post(f"/turnos/{turno_de_ana}/cancelar", json={}, headers=como_alvarez)

    assert respuesta.status_code == 403


def test_paciente_con_el_email_del_profesional_responde_403(cliente, emitir, turno_de_ana):
    """El tipo del token también cuenta: no alcanza con que coincida el email."""
    respuesta = cliente.post(
        f"/turnos/{turno_de_ana}/cancelar", json={}, headers=emitir(GOMEZ, "PACIENTE")
    )

    assert respuesta.status_code == 403


def test_turno_inexistente_responde_404(cliente, como_ana):
    respuesta = cliente.post("/turnos/999/cancelar", json={}, headers=como_ana)

    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "El turno no existe"}


def test_sin_token_responde_401(cliente, turno_de_ana):
    assert cliente.post(f"/turnos/{turno_de_ana}/cancelar", json={}).status_code == 401


def test_ya_cancelado_responde_409(cliente, como_ana, como_gomez, turno_de_ana, fabrica_sesiones):
    cliente.post(f"/turnos/{turno_de_ana}/cancelar", json={}, headers=como_ana)

    respuesta = cliente.post(f"/turnos/{turno_de_ana}/cancelar", json={}, headers=como_gomez)

    assert respuesta.status_code == 409
    assert respuesta.json() == {"detail": "El turno ya no está reservado"}
    turno, eventos = turno_y_eventos(fabrica_sesiones, turno_de_ana)
    assert turno.cancelado_por == "PACIENTE"
    assert [e.tipo for e in eventos] == ["turno.confirmado", "turno.cancelado"]


# --- Plazo del paciente: ahora + 24 h < inicio ---


def test_paciente_justo_24_horas_antes_responde_422(cliente, catalogo, como_ana, fabrica_sesiones):
    id_turno = turno_que_empieza(cliente, catalogo, como_ana, AHORA + datetime.timedelta(hours=24))

    respuesta = cliente.post(f"/turnos/{id_turno}/cancelar", json={}, headers=como_ana)

    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": PLAZO_PACIENTE}
    assert turno_y_eventos(fabrica_sesiones, id_turno)[0].estado == "RESERVADO"


def test_paciente_24_horas_y_un_minuto_antes_puede(cliente, catalogo, como_ana):
    inicio = AHORA + datetime.timedelta(hours=24, minutes=1)
    id_turno = turno_que_empieza(cliente, catalogo, como_ana, inicio)

    respuesta = cliente.post(f"/turnos/{id_turno}/cancelar", json={}, headers=como_ana)

    assert respuesta.status_code == 200


def test_paciente_el_mismo_dia_responde_422(cliente, catalogo, como_ana):
    id_turno = turno_que_empieza(cliente, catalogo, como_ana, AHORA + datetime.timedelta(hours=2))

    respuesta = cliente.post(f"/turnos/{id_turno}/cancelar", json={}, headers=como_ana)

    assert respuesta.status_code == 422


# --- Plazo del profesional: antes del inicio ---


def test_profesional_dentro_de_las_24_horas_puede(cliente, catalogo, como_ana, como_gomez):
    id_turno = turno_que_empieza(cliente, catalogo, como_ana, AHORA + datetime.timedelta(hours=1))

    respuesta = cliente.post(
        f"/turnos/{id_turno}/cancelar", json={"motivo": "Urgencia"}, headers=como_gomez
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["cancelado_por"] == "PROFESIONAL"


def test_profesional_un_minuto_antes_del_inicio_puede(cliente, catalogo, como_ana, como_gomez, reloj_fijo):
    inicio = AHORA + datetime.timedelta(hours=1)
    id_turno = turno_que_empieza(cliente, catalogo, como_ana, inicio)
    reloj_fijo.ahora = inicio - datetime.timedelta(minutes=1)

    respuesta = cliente.post(f"/turnos/{id_turno}/cancelar", json={}, headers=como_gomez)

    assert respuesta.status_code == 200


@pytest.mark.parametrize(
    "despues", [datetime.timedelta(0), datetime.timedelta(minutes=15)], ids=["justo-al-inicio", "ya-empezado"]
)
def test_profesional_despues_del_inicio_responde_422(
    cliente, catalogo, como_ana, como_gomez, reloj_fijo, fabrica_sesiones, despues
):
    inicio = AHORA + datetime.timedelta(hours=1)
    id_turno = turno_que_empieza(cliente, catalogo, como_ana, inicio)
    reloj_fijo.ahora = inicio + despues

    respuesta = cliente.post(f"/turnos/{id_turno}/cancelar", json={}, headers=como_gomez)

    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": YA_EMPEZO}
    assert turno_y_eventos(fabrica_sesiones, id_turno)[0].estado == "RESERVADO"


def test_el_plazo_usa_la_hora_de_montevideo(cliente, catalogo, como_ana, reloj_fijo):
    """El mismo instante expresado en UTC da el mismo resultado."""
    id_turno = turno_que_empieza(cliente, catalogo, como_ana, AHORA + datetime.timedelta(hours=24))
    reloj_fijo.ahora = AHORA.astimezone(datetime.UTC)  # 13:00 UTC = 10:00 Montevideo

    respuesta = cliente.post(f"/turnos/{id_turno}/cancelar", json={}, headers=como_ana)

    assert respuesta.status_code == 422
