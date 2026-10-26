"""Endpoints internos: cada respuesta del contrato de docs/05-comunicacion.md."""

import datetime

import pytest

from app.db.modelos import Disponibilidad, Profesional
from tests.conftest import datos_profesional


def profesionales_en_base(fabrica_sesiones) -> list[tuple[str, str, int]]:
    with fabrica_sesiones() as sesion:
        return [
            (p.email, p.matricula, p.id_especialidad)
            for p in sesion.query(Profesional).order_by(Profesional.email)
        ]


# --- POST /interno/profesionales ---


def test_crear_responde_201(cliente, fabrica_sesiones):
    respuesta = cliente.post("/interno/profesionales", json=datos_profesional())

    assert respuesta.status_code == 201
    assert respuesta.json() == datos_profesional()
    assert profesionales_en_base(fabrica_sesiones) == [("dr.gomez@ejemplo.com", "MP-12345", 1)]


def test_crear_dos_veces_con_los_mismos_datos_responde_200(cliente, fabrica_sesiones):
    cliente.post("/interno/profesionales", json=datos_profesional())

    respuesta = cliente.post("/interno/profesionales", json=datos_profesional())

    assert respuesta.status_code == 200
    assert respuesta.json() == datos_profesional()
    assert len(profesionales_en_base(fabrica_sesiones)) == 1


def test_reintento_con_otro_nombre_actualiza_la_copia(cliente, fabrica_sesiones):
    """Nombre y apellido son una copia para mostrar (ADR 004): no son conflicto."""
    cliente.post("/interno/profesionales", json=datos_profesional())

    respuesta = cliente.post(
        "/interno/profesionales", json=datos_profesional(nombre="Bruno José")
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "Bruno José"
    with fabrica_sesiones() as sesion:
        assert sesion.get(Profesional, "dr.gomez@ejemplo.com").nombre == "Bruno José"


@pytest.mark.parametrize("campo", ["nombre", "apellido"])
def test_crear_sin_nombre_o_apellido_responde_422(cliente, fabrica_sesiones, campo):
    datos = datos_profesional()
    del datos[campo]

    respuesta = cliente.post("/interno/profesionales", json=datos)

    assert respuesta.status_code == 422
    assert profesionales_en_base(fabrica_sesiones) == []


def test_crear_normaliza_el_email(cliente, fabrica_sesiones):
    respuesta = cliente.post(
        "/interno/profesionales", json=datos_profesional(email="Dr.Gomez@Ejemplo.COM")
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["email"] == "dr.gomez@ejemplo.com"
    # Repetir con otra combinación de mayúsculas es el mismo profesional.
    otra_vez = cliente.post(
        "/interno/profesionales", json=datos_profesional(email="DR.GOMEZ@ejemplo.com")
    )
    assert otra_vez.status_code == 200


def test_matricula_de_otro_profesional_responde_409(cliente, fabrica_sesiones):
    cliente.post("/interno/profesionales", json=datos_profesional())

    respuesta = cliente.post(
        "/interno/profesionales", json=datos_profesional(email="otra@ejemplo.com")
    )

    assert respuesta.status_code == 409
    assert respuesta.json() == {
        "detail": "La matrícula ya está registrada",
        "codigo": "MATRICULA_DUPLICADA",
    }
    assert len(profesionales_en_base(fabrica_sesiones)) == 1


@pytest.mark.parametrize(
    "cambios",
    [{"matricula": "MP-99999"}, {"id_especialidad": 2}],
    ids=["otra-matricula", "otra-especialidad"],
)
def test_email_con_otros_datos_responde_409(cliente, fabrica_sesiones, cambios):
    cliente.post("/interno/profesionales", json=datos_profesional())

    respuesta = cliente.post("/interno/profesionales", json=datos_profesional(**cambios))

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "EMAIL_CON_OTROS_DATOS"
    # No se pisan los datos existentes.
    assert profesionales_en_base(fabrica_sesiones) == [("dr.gomez@ejemplo.com", "MP-12345", 1)]


def test_especialidad_inexistente_responde_422(cliente, fabrica_sesiones):
    respuesta = cliente.post(
        "/interno/profesionales", json=datos_profesional(id_especialidad=999)
    )

    assert respuesta.status_code == 422
    assert respuesta.json() == {
        "detail": "La especialidad no existe",
        "codigo": "ESPECIALIDAD_INEXISTENTE",
    }
    assert profesionales_en_base(fabrica_sesiones) == []


@pytest.mark.parametrize(
    "cambios",
    [{"email": "no-es-un-email"}, {"matricula": " "}, {"id_especialidad": 0}],
    ids=["email-invalido", "matricula-vacia", "especialidad-cero"],
)
def test_cuerpo_invalido_responde_422_sin_codigo(cliente, cambios):
    respuesta = cliente.post("/interno/profesionales", json=datos_profesional(**cambios))

    assert respuesta.status_code == 422
    assert "codigo" not in respuesta.json()


# --- DELETE /interno/profesionales/{email} ---


def test_borrar_existente_responde_204(cliente, fabrica_sesiones):
    cliente.post("/interno/profesionales", json=datos_profesional())

    respuesta = cliente.delete("/interno/profesionales/dr.gomez%40ejemplo.com")

    assert respuesta.status_code == 204
    assert respuesta.content == b""
    assert profesionales_en_base(fabrica_sesiones) == []


def test_borrar_inexistente_responde_204(cliente):
    respuesta = cliente.delete("/interno/profesionales/nadie%40ejemplo.com")

    assert respuesta.status_code == 204


def test_borrar_dos_veces_responde_204_las_dos(cliente, fabrica_sesiones):
    cliente.post("/interno/profesionales", json=datos_profesional())

    primera = cliente.delete("/interno/profesionales/dr.gomez%40ejemplo.com")
    segunda = cliente.delete("/interno/profesionales/dr.gomez%40ejemplo.com")

    assert (primera.status_code, segunda.status_code) == (204, 204)
    assert profesionales_en_base(fabrica_sesiones) == []


def test_borrar_normaliza_el_email(cliente, fabrica_sesiones):
    cliente.post("/interno/profesionales", json=datos_profesional())

    respuesta = cliente.delete("/interno/profesionales/DR.Gomez%40Ejemplo.com")

    assert respuesta.status_code == 204
    assert profesionales_en_base(fabrica_sesiones) == []


def test_borrar_con_disponibilidades_responde_409(cliente, fabrica_sesiones):
    cliente.post("/interno/profesionales", json=datos_profesional())
    with fabrica_sesiones() as sesion:
        sesion.add(
            Disponibilidad(
                email_profesional="dr.gomez@ejemplo.com",
                fecha=datetime.date(2026, 11, 2),
                horario_inicio=datetime.time(9, 0),
                horario_fin=datetime.time(9, 30),
            )
        )
        sesion.commit()

    respuesta = cliente.delete("/interno/profesionales/dr.gomez%40ejemplo.com")

    assert respuesta.status_code == 409
    assert respuesta.json() == {
        "detail": "El profesional tiene disponibilidades y no se puede borrar",
        "codigo": "PROFESIONAL_CON_DISPONIBILIDADES",
    }
    assert len(profesionales_en_base(fabrica_sesiones)) == 1


def test_crear_borrar_y_crear_de_nuevo(cliente):
    """Una compensación seguida de un reintento del registro."""
    assert cliente.post("/interno/profesionales", json=datos_profesional()).status_code == 201
    assert cliente.delete("/interno/profesionales/dr.gomez%40ejemplo.com").status_code == 204
    assert cliente.post("/interno/profesionales", json=datos_profesional()).status_code == 201


# --- GET /interno/disponibilidades/{id}?id_servicio= (lo usa reservas) ---


@pytest.fixture
def franja_de_gomez(cliente, fabrica_sesiones) -> int:
    cliente.post("/interno/profesionales", json=datos_profesional())
    with fabrica_sesiones() as sesion:
        franja = Disponibilidad(
            email_profesional="dr.gomez@ejemplo.com",
            fecha=datetime.date(2026, 11, 5),
            horario_inicio=datetime.time(9, 0),
            horario_fin=datetime.time(9, 30),
        )
        sesion.add(franja)
        sesion.commit()
        return franja.id_disponibilidad


def test_datos_para_reservar(cliente, franja_de_gomez):
    # Servicio 1 = "Consulta general", de clínica médica (especialidad 1).
    respuesta = cliente.get(f"/interno/disponibilidades/{franja_de_gomez}?id_servicio=1")

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "id_disponibilidad": franja_de_gomez,
        "email_profesional": "dr.gomez@ejemplo.com",
        "fecha": "2026-11-05",
        "horario_inicio": "09:00:00",
        "horario_fin": "09:30:00",
        "id_especialidad": 1,
        "servicio": {"id_servicio": 1, "nombre": "Consulta general", "id_especialidad": 1},
    }


def test_datos_para_reservar_informa_aunque_el_servicio_no_corresponda(cliente, franja_de_gomez):
    """Catálogo solo informa; la coherencia del servicio la decide reservas."""
    # Servicio 3 = "Control del niño sano", de pediatría (especialidad 2).
    respuesta = cliente.get(f"/interno/disponibilidades/{franja_de_gomez}?id_servicio=3")

    assert respuesta.status_code == 200
    assert respuesta.json()["id_especialidad"] == 1
    assert respuesta.json()["servicio"]["id_especialidad"] == 2


def test_datos_para_reservar_disponibilidad_inexistente(cliente):
    respuesta = cliente.get("/interno/disponibilidades/999?id_servicio=1")

    assert respuesta.status_code == 404
    assert respuesta.json() == {
        "detail": "La disponibilidad no existe",
        "codigo": "DISPONIBILIDAD_INEXISTENTE",
    }


def test_datos_para_reservar_servicio_inexistente(cliente, franja_de_gomez):
    respuesta = cliente.get(f"/interno/disponibilidades/{franja_de_gomez}?id_servicio=999")

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "SERVICIO_INEXISTENTE"


def test_datos_para_reservar_sin_servicio_responde_422(cliente, franja_de_gomez):
    respuesta = cliente.get(f"/interno/disponibilidades/{franja_de_gomez}")

    assert respuesta.status_code == 422
