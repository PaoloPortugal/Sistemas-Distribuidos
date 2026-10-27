"""Adaptador de correo: SMTP (Mailpit en desarrollo)."""

import smtplib
from email.message import EmailMessage
from email.utils import formatdate

from app.config import configuracion


class ServidorSmtp:
    def __init__(self, host: str, puerto: int, remitente: str, timeout: float):
        self._host = host
        self._puerto = puerto
        self._remitente = remitente
        self._timeout = timeout

    def enviar(self, *, para: str, asunto: str, cuerpo: str, id_mensaje: str) -> None:
        mensaje = EmailMessage()
        mensaje["From"] = self._remitente
        mensaje["To"] = para
        mensaje["Subject"] = asunto
        mensaje["Date"] = formatdate(localtime=True)
        # Fijo por notificación: si el mail se reenvía, es el mismo Message-ID.
        mensaje["Message-ID"] = f"<{id_mensaje}@{self._remitente.split('@')[-1]}>"
        mensaje.set_content(cuerpo)
        with smtplib.SMTP(self._host, self._puerto, timeout=self._timeout) as servidor:
            servidor.send_message(mensaje)


def servidor_configurado() -> ServidorSmtp:
    return ServidorSmtp(
        configuracion.smtp_host,
        configuracion.smtp_puerto,
        configuracion.smtp_remitente,
        configuracion.smtp_timeout_segundos,
    )
