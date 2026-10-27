"""Consumidor: idempotencia, DLQ y ack después del commit (ADR 008)."""

import asyncio

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.consumidor import procesar
from app.db.modelos import EnvioMail, EventoProcesado, Notificacion
from tests.conftest import MensajeFalso, evento


def contenido(fabrica):
    with fabrica() as sesion:
        notificaciones = sesion.query(Notificacion).order_by(Notificacion.id_notificacion).all()
        return (
            [(n.id_turno, n.tipo, n.destinatario, n.estado_notificacion) for n in notificaciones],
            sesion.query(EnvioMail).count(),
            sesion.query(EventoProcesado).count(),
        )


def consumir(fabrica, mensaje) -> str:
    return asyncio.run(procesar(mensaje, fabrica))


def test_un_evento_crea_dos_notificaciones_y_dos_envios(fabrica_sesiones):
    mensaje = MensajeFalso(evento())

    assert consumir(fabrica_sesiones, mensaje) == "nuevo"

    notificaciones, envios, procesados = contenido(fabrica_sesiones)
    assert notificaciones == [
        (15, "CONFIRMADO", "PACIENTE", "PENDIENTE"),
        (15, "CONFIRMADO", "PROFESIONAL", "PENDIENTE"),
    ]
    assert (envios, procesados) == (2, 1)
    assert mensaje.bitacora == ["ack"]
    with fabrica_sesiones() as sesion:
        destinos = {e.notificacion.destinatario: e.email_destinatario for e in sesion.query(EnvioMail)}
    assert destinos == {"PACIENTE": "ana.perez@ejemplo.com", "PROFESIONAL": "dr.gomez@ejemplo.com"}


def test_el_mismo_evento_dos_veces_no_crea_nada_nuevo(fabrica_sesiones):
    datos = evento()
    primero, segundo = MensajeFalso(datos), MensajeFalso(datos)

    assert consumir(fabrica_sesiones, primero) == "nuevo"
    assert consumir(fabrica_sesiones, segundo) == "duplicado"

    notificaciones, envios, procesados = contenido(fabrica_sesiones)
    assert (len(notificaciones), envios, procesados) == (2, 2, 1)
    assert segundo.bitacora == ["ack"]  # el duplicado se confirma igual, para que no vuelva


def test_otro_evento_para_el_mismo_turno_y_tipo_no_duplica(fabrica_sesiones):
    """Defensa extra: UNIQUE (id_turno, tipo, destinatario)."""
    consumir(fabrica_sesiones, MensajeFalso(evento()))

    resultado = consumir(fabrica_sesiones, MensajeFalso(evento()))  # otro id_evento

    assert resultado == "duplicado"
    assert len(contenido(fabrica_sesiones)[0]) == 2


def test_confirmacion_y_cancelacion_del_mismo_turno(fabrica_sesiones):
    consumir(fabrica_sesiones, MensajeFalso(evento()))
    consumir(fabrica_sesiones, MensajeFalso(evento("turno.cancelado")))

    notificaciones, envios, procesados = contenido(fabrica_sesiones)
    assert [(n[1], n[2]) for n in notificaciones] == [
        ("CONFIRMADO", "PACIENTE"),
        ("CONFIRMADO", "PROFESIONAL"),
        ("CANCELADO", "PACIENTE"),
        ("CANCELADO", "PROFESIONAL"),
    ]
    assert (envios, procesados) == (4, 2)


@pytest.mark.parametrize(
    "cuerpo",
    [
        b"esto no es json",
        b'{"tipo": "turno.confirmado"}',
        evento(tipo="turno.modificado"),
        evento(id_evento="no-es-un-uuid"),
        evento(email_paciente="no-es-un-email"),
        evento(tipo="turno.cancelado", cancelado_por=None),
    ],
    ids=["no-json", "faltan-campos", "tipo-inexistente", "id-invalido", "email-invalido", "cancelado-sin-quien"],
)
def test_mensaje_invalido_va_a_la_dlq(fabrica_sesiones, cuerpo):
    mensaje = MensajeFalso(cuerpo)

    assert consumir(fabrica_sesiones, mensaje) == "invalido"

    assert mensaje.bitacora == ["reject(requeue=False)"]  # → turnos.dlx → DLQ
    assert contenido(fabrica_sesiones) == ([], 0, 0)


def test_el_ack_va_despues_del_commit(fabrica_sesiones):
    bitacora: list[str] = []
    mensaje = MensajeFalso(evento(), bitacora)

    @event.listens_for(Session, "after_commit")
    def anotar_commit(_sesion):
        bitacora.append("commit")

    try:
        consumir(fabrica_sesiones, mensaje)
    finally:
        event.remove(Session, "after_commit", anotar_commit)

    assert bitacora == ["commit", "ack"]


class SesionSinBase(Session):
    def commit(self):
        raise OperationalError("COMMIT", {}, Exception("la base no responde"))


def test_si_la_base_falla_no_hay_ack_y_se_reencola(motor, fabrica_sesiones):
    mensaje = MensajeFalso(evento())
    esperas = []

    async def esperar_base():
        esperas.append("esperó a la base")

    resultado = asyncio.run(
        procesar(mensaje, sessionmaker(bind=motor, class_=SesionSinBase), esperar_base)
    )

    assert resultado == "reencolado"
    assert esperas == ["esperó a la base"]
    assert mensaje.bitacora == ["nack(requeue=True)"]  # cuenta para x-delivery-limit
    assert contenido(fabrica_sesiones) == ([], 0, 0)
