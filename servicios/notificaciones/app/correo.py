"""Adaptador SMTP; en desarrollo apunta a Mailpit."""

import asyncio
import smtplib
from email.message import EmailMessage

from app.config import configuracion


async def enviar_notificacion(
    *,
    destinatario: str,
    asunto: str,
    cuerpo: str,
) -> None:
    mensaje = EmailMessage()
    mensaje["From"] = "turnos@clinica.local"
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content(cuerpo)
    await asyncio.to_thread(_enviar_smtp, mensaje)


def _enviar_smtp(mensaje: EmailMessage) -> None:
    with smtplib.SMTP(configuracion.smtp_host, configuracion.smtp_puerto, timeout=10) as smtp:
        smtp.send_message(mensaje)
