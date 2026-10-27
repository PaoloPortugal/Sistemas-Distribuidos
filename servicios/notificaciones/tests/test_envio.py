"""Envío de mails: PENDIENTE → ENVIADO / FALLIDO, con espera creciente (ADR 008)."""

import asyncio
import datetime

import pytest

from app.consumidor import procesar
from app.db.modelos import EnvioMail, Notificacion
from app.dominio.envio import PoliticaReintentos, enviar_pendientes
from tests.conftest import AHORA, CorreoFalso, MensajeFalso, evento

POLITICA = PoliticaReintentos(max_intentos=8, espera_minima=5, espera_maxima=60)
PACIENTE = "ana.perez@ejemplo.com"
PROFESIONAL = "dr.gomez@ejemplo.com"


@pytest.fixture
def con_un_evento(fabrica_sesiones):
    asyncio.run(procesar(MensajeFalso(evento()), fabrica_sesiones))


def estados(fabrica) -> dict[str, tuple]:
    with fabrica() as sesion:
        return {
            e.email_destinatario: (
                e.notificacion.estado_notificacion,
                e.intentos,
                e.proximo_intento.replace(tzinfo=datetime.UTC),  # SQLite no guarda la zona
                e.ultimo_error,
            )
            for e in sesion.query(EnvioMail)
        }


def enviar(fabrica, correo, momento=AHORA):
    return enviar_pendientes(fabrica, correo, POLITICA, ahora=lambda: momento)


def test_pendiente_pasa_a_enviado(fabrica_sesiones, con_un_evento):
    correo = CorreoFalso()

    resultado = enviar(fabrica_sesiones, correo)

    assert (resultado.enviados, resultado.reprogramados, resultado.fallidos) == (2, 0, 0)
    assert {m["para"] for m in correo.enviados} == {PACIENTE, PROFESIONAL}
    assert {e[0] for e in estados(fabrica_sesiones).values()} == {"ENVIADO"}
    # Un segundo ciclo no vuelve a mandar nada.
    assert enviar(fabrica_sesiones, correo).procesados == 0
    assert len(correo.enviados) == 2


def test_el_message_id_es_fijo_por_notificacion(fabrica_sesiones, con_un_evento):
    correo = CorreoFalso()
    enviar(fabrica_sesiones, correo)

    with fabrica_sesiones() as sesion:
        ids = {f"notificacion-{n.id_notificacion}" for n in sesion.query(Notificacion)}
    assert {m["id"] for m in correo.enviados} == ids


def test_si_falla_el_del_paciente_el_del_profesional_sale_igual(fabrica_sesiones, con_un_evento):
    correo = CorreoFalso()
    correo.fallar_para = {PACIENTE}

    resultado = enviar(fabrica_sesiones, correo)

    assert (resultado.enviados, resultado.reprogramados) == (1, 1)
    assert [m["para"] for m in correo.enviados] == [PROFESIONAL]
    situacion = estados(fabrica_sesiones)
    assert situacion[PROFESIONAL][0] == "ENVIADO"
    assert situacion[PACIENTE][:2] == ("PENDIENTE", 1)
    assert situacion[PACIENTE][3] == "ConnectionRefusedError: SMTP no disponible"


def test_la_espera_crece_entre_intentos(fabrica_sesiones, con_un_evento):
    correo = CorreoFalso()
    correo.fallar_para = {PACIENTE}
    momento = AHORA
    esperas = []

    for _ in range(7):
        enviar(fabrica_sesiones, correo, momento)
        proximo = estados(fabrica_sesiones)[PACIENTE][2]
        esperas.append((proximo - momento).total_seconds())
        momento = proximo  # el siguiente ciclo corre justo cuando vence la espera

    assert esperas == [5, 10, 20, 40, 60, 60, 60]


def test_no_reintenta_antes_de_tiempo(fabrica_sesiones, con_un_evento):
    correo = CorreoFalso()
    correo.fallar_para = {PACIENTE}
    enviar(fabrica_sesiones, correo)  # intento 1: próximo en 5 s
    correo.fallar_para.clear()

    assert enviar(fabrica_sesiones, correo, AHORA + datetime.timedelta(seconds=4)).procesados == 0
    assert enviar(fabrica_sesiones, correo, AHORA + datetime.timedelta(seconds=5)).enviados == 1


def test_tras_n_errores_pasa_a_fallido(fabrica_sesiones, con_un_evento):
    correo = CorreoFalso()
    correo.fallar_para = {PACIENTE}
    momento = AHORA

    for _ in range(POLITICA.max_intentos):
        enviar(fabrica_sesiones, correo, momento)
        momento += datetime.timedelta(minutes=5)

    estado, intentos, _, _ = estados(fabrica_sesiones)[PACIENTE]
    assert (estado, intentos) == ("FALLIDO", 8)
    # Un FALLIDO no se vuelve a intentar, aunque el servidor vuelva.
    correo.fallar_para.clear()
    assert enviar(fabrica_sesiones, correo, momento + datetime.timedelta(hours=1)).procesados == 0


def test_cuando_el_servidor_vuelve_se_envia(fabrica_sesiones, con_un_evento):
    correo = CorreoFalso()
    correo.fallar_para = {PACIENTE, PROFESIONAL}
    enviar(fabrica_sesiones, correo)
    enviar(fabrica_sesiones, correo, AHORA + datetime.timedelta(seconds=5))
    assert {e[:2] for e in estados(fabrica_sesiones).values()} == {("PENDIENTE", 2)}

    correo.fallar_para.clear()
    resultado = enviar(fabrica_sesiones, correo, AHORA + datetime.timedelta(seconds=15))

    assert resultado.enviados == 2
    assert {e[0] for e in estados(fabrica_sesiones).values()} == {"ENVIADO"}
