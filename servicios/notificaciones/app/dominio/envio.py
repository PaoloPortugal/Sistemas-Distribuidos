"""Envío de los mails pendientes: PENDIENTE → ENVIADO, o FALLIDO tras N intentos.

Cada NOTIFICACION se envía en su propia transacción y la toma con
`FOR UPDATE SKIP LOCKED`, así dos procesos de envío no mandan la misma. Si un
mail falla, solo se reprograma ese: los demás (por ejemplo, el del otro
destinatario del mismo turno) salen igual.

Ventana de duplicado (ADR 008): el SMTP no participa de la transacción. Si el
proceso se cae después de que el servidor aceptó el mail y antes del commit,
ese mail se vuelve a mandar. No existe "exactamente una vez" con un efecto
externo; la ventana es lo que tarda el commit.
"""

import datetime
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.modelos import ENVIADO, FALLIDO, PENDIENTE, EnvioMail, Notificacion


class ServidorCorreo(Protocol):
    def enviar(self, *, para: str, asunto: str, cuerpo: str, id_mensaje: str) -> None:
        """Manda el mail; si el servidor no lo acepta, lanza una excepción."""


@dataclass(frozen=True)
class PoliticaReintentos:
    max_intentos: int
    espera_minima: float
    espera_maxima: float

    def espera(self, intentos: int) -> datetime.timedelta:
        """Espera creciente: mínima, el doble, el doble… hasta la máxima."""
        segundos = min(self.espera_minima * 2 ** (intentos - 1), self.espera_maxima)
        return datetime.timedelta(seconds=segundos)


@dataclass
class Resultado:
    enviados: int = 0
    reprogramados: int = 0
    fallidos: int = 0

    @property
    def procesados(self) -> int:
        return self.enviados + self.reprogramados + self.fallidos


def _siguiente(sesion: Session, ahora: datetime.datetime) -> Notificacion | None:
    consulta = (
        select(Notificacion)
        .join(EnvioMail)
        .where(
            Notificacion.estado_notificacion == PENDIENTE,
            EnvioMail.proximo_intento <= ahora,
        )
        .order_by(EnvioMail.proximo_intento, Notificacion.id_notificacion)
        .limit(1)
        .with_for_update(skip_locked=True, of=Notificacion)
    )
    return sesion.scalars(consulta).first()


def enviar_pendientes(
    fabrica_sesiones: Callable[[], Session],
    correo: ServidorCorreo,
    politica: PoliticaReintentos,
    *,
    ahora: Callable[[], datetime.datetime],
    lote: int = 50,
) -> Resultado:
    resultado = Resultado()
    while resultado.procesados < lote:
        with fabrica_sesiones() as sesion:
            momento = ahora()
            notificacion = _siguiente(sesion, momento)
            if notificacion is None:
                break
            envio = notificacion.envio
            try:
                correo.enviar(
                    para=envio.email_destinatario,
                    asunto=envio.asunto,
                    cuerpo=envio.cuerpo,
                    id_mensaje=f"notificacion-{notificacion.id_notificacion}",
                )
            except Exception as error:
                envio.intentos += 1
                envio.ultimo_error = f"{type(error).__name__}: {error}"[:1000]
                if envio.intentos >= politica.max_intentos:
                    notificacion.estado_notificacion = FALLIDO
                    resultado.fallidos += 1
                else:
                    envio.proximo_intento = momento + politica.espera(envio.intentos)
                    resultado.reprogramados += 1
            else:
                envio.intentos += 1
                envio.enviado_en = momento
                notificacion.estado_notificacion = ENVIADO
                resultado.enviados += 1
            sesion.commit()
    return resultado
