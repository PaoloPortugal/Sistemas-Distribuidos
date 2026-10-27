"""Textos de los mails: uno para el paciente y otro para el profesional.

Usan solo los datos del evento, sin consultar a otros servicios: por eso
nombran a las personas por su email (ADR 008, opción C de los nombres).
"""

from dataclasses import dataclass

from app.db.modelos import PACIENTE, PROFESIONAL
from app.dominio.eventos import TURNO_CONFIRMADO, EventoTurno

FIRMA = "\n\nClínica — sistema de turnos"


@dataclass(frozen=True)
class Mail:
    destinatario: str  # PACIENTE o PROFESIONAL
    email: str
    asunto: str
    cuerpo: str


def armar_mails(evento: EventoTurno) -> list[Mail]:
    """Los dos mails de un evento: [paciente, profesional]."""
    fecha = evento.fecha.strftime("%d/%m/%Y")
    inicio = evento.horario_inicio.strftime("%H:%M")
    fin = evento.horario_fin.strftime("%H:%M")
    cuando = f"el {fecha} de {inicio} a {fin}"
    numero = f"Turno #{evento.id_turno}"

    if evento.tipo == TURNO_CONFIRMADO:
        return [
            Mail(
                PACIENTE,
                evento.email_paciente,
                f"{numero} confirmado: {fecha} {inicio}",
                f"Hola,\n\nTu turno quedó confirmado para {cuando} con "
                f"{evento.email_profesional}.\n\nSi no podés asistir, podés cancelarlo "
                f"hasta 24 horas antes." + FIRMA,
            ),
            Mail(
                PROFESIONAL,
                evento.email_profesional,
                f"Nuevo turno #{evento.id_turno}: {fecha} {inicio}",
                f"Hola,\n\nTenés un nuevo turno {cuando} con {evento.email_paciente}." + FIRMA,
            ),
        ]

    motivo = f"\nMotivo: {evento.motivo}" if evento.motivo else ""
    asunto = f"{numero} cancelado: {fecha} {inicio}"
    if evento.cancelado_por == PACIENTE:
        al_paciente = "Cancelaste tu turno"
        al_profesional = f"El paciente {evento.email_paciente} canceló el turno"
    else:
        al_paciente = f"El profesional {evento.email_profesional} canceló tu turno"
        al_profesional = "Cancelaste el turno"
    return [
        Mail(
            PACIENTE,
            evento.email_paciente,
            asunto,
            f"Hola,\n\n{al_paciente} {cuando} con {evento.email_profesional}.{motivo}" + FIRMA,
        ),
        Mail(
            PROFESIONAL,
            evento.email_profesional,
            asunto,
            f"Hola,\n\n{al_profesional} {cuando} con {evento.email_paciente}.{motivo}" + FIRMA,
        ),
    ]
