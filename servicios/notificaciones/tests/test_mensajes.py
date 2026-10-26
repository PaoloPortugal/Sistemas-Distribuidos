"""Textos de los mails para paciente y profesional."""

from app.dominio.eventos import interpretar
from app.dominio.mensajes import armar_mails
from tests.conftest import evento

import json


def mails(**datos):
    paciente, profesional = armar_mails(interpretar(json.dumps(evento(**datos)).encode()))
    assert (paciente.destinatario, profesional.destinatario) == ("PACIENTE", "PROFESIONAL")
    assert (paciente.email, profesional.email) == ("ana.perez@ejemplo.com", "dr.gomez@ejemplo.com")
    return paciente, profesional


def test_confirmado():
    paciente, profesional = mails()

    assert paciente.asunto == "Turno #15 confirmado: 05/11/2026 09:00"
    assert "Tu turno quedó confirmado para el 05/11/2026 de 09:00 a 09:30 con dr.gomez@ejemplo.com." in paciente.cuerpo
    assert profesional.asunto == "Nuevo turno #15: 05/11/2026 09:00"
    assert "Tenés un nuevo turno el 05/11/2026 de 09:00 a 09:30 con ana.perez@ejemplo.com." in profesional.cuerpo


def test_cancelado_por_el_paciente_con_motivo():
    paciente, profesional = mails(tipo="turno.cancelado")

    assert paciente.asunto == profesional.asunto == "Turno #15 cancelado: 05/11/2026 09:00"
    assert "Cancelaste tu turno el 05/11/2026 de 09:00 a 09:30 con dr.gomez@ejemplo.com." in paciente.cuerpo
    assert "El paciente ana.perez@ejemplo.com canceló el turno el 05/11/2026" in profesional.cuerpo
    assert "Motivo: Viaje" in paciente.cuerpo and "Motivo: Viaje" in profesional.cuerpo


def test_cancelado_por_el_profesional_sin_motivo():
    datos = evento(tipo="turno.cancelado", cancelado_por="PROFESIONAL", motivo=None)
    paciente, profesional = armar_mails(interpretar(json.dumps(datos).encode()))

    assert "El profesional dr.gomez@ejemplo.com canceló tu turno el 05/11/2026" in paciente.cuerpo
    assert "Cancelaste el turno el 05/11/2026 de 09:00 a 09:30 con ana.perez@ejemplo.com." in profesional.cuerpo
    assert "Motivo" not in paciente.cuerpo + profesional.cuerpo
