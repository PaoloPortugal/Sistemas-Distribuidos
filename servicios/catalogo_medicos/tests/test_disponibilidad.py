"""Endpoints de disponibilidad. El reloj está fijo en AHORA (lunes 2/11/2026 10:00)."""

import pytest

from app.db.modelos import Disponibilidad

GOMEZ = "dr.gomez@ejemplo.com"


def franja(fecha="2026-11-03", inicio="09:00", fin="09:30") -> dict:
    return {"fecha": fecha, "horario_inicio": inicio, "horario_fin": fin}


@pytest.fixture
def como_gomez(emitir, profesionales) -> dict:
    return emitir(GOMEZ, "PROFESIONAL")


@pytest.fixture
def como_paciente(emitir) -> dict:
    return emitir("ana.perez@ejemplo.com", "PACIENTE")


def franjas_en_base(fabrica_sesiones) -> list[tuple]:
    with fabrica_sesiones() as sesion:
        return [
            (d.email_profesional, d.fecha.isoformat(), d.horario_inicio.strftime("%H:%M"))
            for d in sesion.query(Disponibilidad).order_by(
                Disponibilidad.fecha, Disponibilidad.horario_inicio
            )
        ]


# --- POST /disponibilidades ---


def test_crear_franja_propia(cliente, como_gomez, fabrica_sesiones):
    respuesta = cliente.post("/disponibilidades", json=franja(), headers=como_gomez)

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo == {
        "id_disponibilidad": cuerpo["id_disponibilidad"],
        "email_profesional": GOMEZ,
        "fecha": "2026-11-03",
        "horario_inicio": "09:00:00",
        "horario_fin": "09:30:00",
    }
    assert franjas_en_base(fabrica_sesiones) == [(GOMEZ, "2026-11-03", "09:00")]


def test_el_email_sale_del_token_y_no_del_cuerpo(cliente, como_gomez, fabrica_sesiones):
    datos = franja() | {"email_profesional": "dra.alvarez@ejemplo.com"}

    respuesta = cliente.post("/disponibilidades", json=datos, headers=como_gomez)

    assert respuesta.status_code == 201
    assert respuesta.json()["email_profesional"] == GOMEZ
    assert franjas_en_base(fabrica_sesiones) == [(GOMEZ, "2026-11-03", "09:00")]


def test_sin_token_responde_401(cliente, profesionales):
    assert cliente.post("/disponibilidades", json=franja()).status_code == 401


def test_token_invalido_responde_401(cliente, profesionales):
    respuesta = cliente.post(
        "/disponibilidades", json=franja(), headers={"Authorization": "Bearer x.y.z"}
    )

    assert respuesta.status_code == 401


def test_paciente_no_puede_crear_responde_403(cliente, como_paciente, fabrica_sesiones):
    respuesta = cliente.post("/disponibilidades", json=franja(), headers=como_paciente)

    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": "Solo para profesionales"}
    assert franjas_en_base(fabrica_sesiones) == []


def test_profesional_que_no_esta_en_el_catalogo_responde_403(cliente, emitir, profesionales):
    respuesta = cliente.post(
        "/disponibilidades", json=franja(), headers=emitir("huerfano@ejemplo.com", "PROFESIONAL")
    )

    assert respuesta.status_code == 403
    assert "no está registrado como profesional" in respuesta.json()["detail"]


@pytest.mark.parametrize(
    ("inicio", "fin"),
    [("10:00", "10:00"), ("11:00", "10:00")],
    ids=["inicio-igual-fin", "inicio-despues-de-fin"],
)
def test_inicio_no_anterior_al_fin_responde_422(cliente, como_gomez, fabrica_sesiones, inicio, fin):
    respuesta = cliente.post(
        "/disponibilidades", json=franja(inicio=inicio, fin=fin), headers=como_gomez
    )

    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": "El horario de inicio tiene que ser anterior al de fin"}
    assert franjas_en_base(fabrica_sesiones) == []


@pytest.mark.parametrize(
    ("fecha", "inicio", "fin"),
    [
        ("2026-11-01", "15:00", "15:30"),  # ayer
        ("2026-11-02", "09:00", "09:30"),  # hoy, ya pasó
        ("2026-11-02", "10:00", "10:30"),  # hoy, empieza justo ahora
    ],
    ids=["ayer", "hoy-ya-paso", "hoy-empieza-ahora"],
)
def test_franja_en_el_pasado_responde_422(cliente, como_gomez, fabrica_sesiones, fecha, inicio, fin):
    respuesta = cliente.post(
        "/disponibilidades", json=franja(fecha, inicio, fin), headers=como_gomez
    )

    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": "No se pueden crear franjas en el pasado"}
    assert franjas_en_base(fabrica_sesiones) == []


def test_hoy_mas_tarde_se_puede(cliente, como_gomez):
    respuesta = cliente.post(
        "/disponibilidades", json=franja("2026-11-02", "10:30", "11:00"), headers=como_gomez
    )

    assert respuesta.status_code == 201


@pytest.mark.parametrize(
    ("inicio", "fin"),
    [("09:15", "09:45"), ("08:45", "09:15"), ("09:00", "09:30"), ("08:00", "12:00")],
    ids=["empieza-adentro", "termina-adentro", "misma-franja", "la-contiene"],
)
def test_franja_superpuesta_responde_409(cliente, como_gomez, fabrica_sesiones, inicio, fin):
    cliente.post("/disponibilidades", json=franja(), headers=como_gomez)

    respuesta = cliente.post(
        "/disponibilidades", json=franja(inicio=inicio, fin=fin), headers=como_gomez
    )

    assert respuesta.status_code == 409
    assert respuesta.json() == {
        "detail": "Se superpone con la franja del 2026-11-03 de 09:00 a 09:30"
    }
    assert len(franjas_en_base(fabrica_sesiones)) == 1


@pytest.mark.parametrize(
    ("fecha", "inicio", "fin"),
    [("2026-11-03", "09:30", "10:00"), ("2026-11-03", "08:30", "09:00"), ("2026-11-04", "09:00", "09:30")],
    ids=["contigua-despues", "contigua-antes", "otro-dia"],
)
def test_franjas_que_no_se_superponen(cliente, como_gomez, fecha, inicio, fin):
    cliente.post("/disponibilidades", json=franja(), headers=como_gomez)

    respuesta = cliente.post("/disponibilidades", json=franja(fecha, inicio, fin), headers=como_gomez)

    assert respuesta.status_code == 201


def test_otro_profesional_puede_usar_el_mismo_horario(cliente, emitir, como_gomez):
    cliente.post("/disponibilidades", json=franja(), headers=como_gomez)

    respuesta = cliente.post(
        "/disponibilidades",
        json=franja(),
        headers=emitir("dra.alvarez@ejemplo.com", "PROFESIONAL"),
    )

    assert respuesta.status_code == 201


def test_cuerpo_invalido_responde_422(cliente, como_gomez):
    respuesta = cliente.post(
        "/disponibilidades", json={"fecha": "mañana", "horario_inicio": "9"}, headers=como_gomez
    )

    assert respuesta.status_code == 422


# --- GET /mis-disponibilidades ---


@pytest.fixture
def franjas_de_gomez(cliente, como_gomez):
    for fecha, inicio, fin in [
        ("2026-11-03", "09:00", "09:30"),
        ("2026-11-02", "15:00", "15:30"),
        ("2026-12-01", "09:00", "09:30"),  # a 29 días: entra en el rango por defecto
        ("2026-12-10", "09:00", "09:30"),  # a 38 días: queda afuera
    ]:
        assert cliente.post(
            "/disponibilidades", json=franja(fecha, inicio, fin), headers=como_gomez
        ).status_code == 201


def test_mis_disponibilidades_por_defecto_hoy_y_30_dias(cliente, como_gomez, franjas_de_gomez):
    respuesta = cliente.get("/mis-disponibilidades", headers=como_gomez)

    assert respuesta.status_code == 200
    assert [(d["fecha"], d["horario_inicio"]) for d in respuesta.json()] == [
        ("2026-11-02", "15:00:00"),
        ("2026-11-03", "09:00:00"),
        ("2026-12-01", "09:00:00"),
    ]


def test_mis_disponibilidades_con_rango(cliente, como_gomez, franjas_de_gomez):
    respuesta = cliente.get(
        "/mis-disponibilidades?desde=2026-11-03&hasta=2026-12-10", headers=como_gomez
    )

    assert [d["fecha"] for d in respuesta.json()] == ["2026-11-03", "2026-12-01", "2026-12-10"]


def test_mis_disponibilidades_solo_las_propias(cliente, emitir, franjas_de_gomez):
    respuesta = cliente.get(
        "/mis-disponibilidades", headers=emitir("dra.alvarez@ejemplo.com", "PROFESIONAL")
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == []


def test_mis_disponibilidades_sin_token_responde_401(cliente):
    assert cliente.get("/mis-disponibilidades").status_code == 401


def test_mis_disponibilidades_de_paciente_responde_403(cliente, como_paciente):
    respuesta = cliente.get("/mis-disponibilidades", headers=como_paciente)

    assert respuesta.status_code == 403


def test_mis_disponibilidades_profesional_fuera_del_catalogo_responde_403(cliente, emitir):
    respuesta = cliente.get(
        "/mis-disponibilidades", headers=emitir("huerfano@ejemplo.com", "PROFESIONAL")
    )

    assert respuesta.status_code == 403


# --- GET /profesionales/{email}/disponibilidades ---


def test_disponibilidades_de_un_profesional(cliente, como_paciente, franjas_de_gomez):
    respuesta = cliente.get(
        "/profesionales/dr.gomez%40ejemplo.com/disponibilidades", headers=como_paciente
    )

    assert respuesta.status_code == 200
    assert [d["fecha"] for d in respuesta.json()] == ["2026-11-02", "2026-11-03", "2026-12-01"]
    assert all(d["email_profesional"] == GOMEZ for d in respuesta.json())


def test_disponibilidades_con_rango(cliente, como_paciente, franjas_de_gomez):
    respuesta = cliente.get(
        "/profesionales/dr.gomez%40ejemplo.com/disponibilidades?desde=2026-11-03&hasta=2026-11-03",
        headers=como_paciente,
    )

    assert [d["fecha"] for d in respuesta.json()] == ["2026-11-03"]


def test_disponibilidades_email_en_mayusculas(cliente, como_paciente, franjas_de_gomez):
    respuesta = cliente.get(
        "/profesionales/DR.Gomez%40Ejemplo.com/disponibilidades", headers=como_paciente
    )

    assert respuesta.status_code == 200
    assert len(respuesta.json()) == 3


def test_disponibilidades_de_profesional_inexistente_responde_404(cliente, como_paciente):
    respuesta = cliente.get(
        "/profesionales/nadie%40ejemplo.com/disponibilidades", headers=como_paciente
    )

    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "El profesional no existe"}


@pytest.mark.parametrize(
    ("consulta", "mensaje"),
    [
        ("desde=2026-11-10&hasta=2026-11-09", "'desde' no puede ser posterior a 'hasta'"),
        ("desde=2026-11-01&hasta=2027-02-01", "El rango no puede superar 90 días"),
    ],
    ids=["desde-despues-de-hasta", "mas-de-90-dias"],
)
def test_rango_invalido_responde_422(cliente, como_paciente, profesionales, consulta, mensaje):
    respuesta = cliente.get(
        f"/profesionales/dr.gomez%40ejemplo.com/disponibilidades?{consulta}",
        headers=como_paciente,
    )

    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": mensaje}


def test_rango_de_exactamente_90_dias_es_valido(cliente, como_paciente, profesionales):
    respuesta = cliente.get(
        "/profesionales/dr.gomez%40ejemplo.com/disponibilidades?desde=2026-11-01&hasta=2027-01-30",
        headers=como_paciente,
    )

    assert respuesta.status_code == 200
