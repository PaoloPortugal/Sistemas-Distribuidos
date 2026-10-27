"""Publicador del outbox (ADR 005), con un broker falso en lugar de RabbitMQ."""

import asyncio
import datetime
import uuid

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.db.modelos import EventoSaliente
from app.dominio.publicacion import publicar_pendientes

INICIO = datetime.datetime(2026, 11, 2, 13, 0, tzinfo=datetime.UTC)
PUBLICADO = datetime.datetime(2026, 11, 2, 13, 5, tzinfo=datetime.UTC)


class BrokerFalso:
    """Registra lo publicado; puede rechazar la confirmación de ciertos eventos."""

    def __init__(self, rechazar: set[int] | None = None):
        self.publicados: list[int] = []
        self.rechazar = rechazar or set()

    async def publicar(self, evento: EventoSaliente) -> None:
        numero = evento.payload["numero"]
        if numero in self.rechazar:
            raise RuntimeError("el broker no confirmó")  # Nack o conexión perdida
        self.publicados.append(numero)


def cargar_eventos(fabrica: sessionmaker[Session], cantidad: int) -> None:
    """Eventos 1..cantidad, insertados en orden inverso para probar el orden."""
    with fabrica() as sesion:
        for numero in reversed(range(1, cantidad + 1)):
            sesion.add(
                EventoSaliente(
                    id_evento=uuid.uuid4(),
                    tipo="turno.confirmado",
                    payload={"numero": numero},
                    creado_en=INICIO + datetime.timedelta(seconds=numero),
                )
            )
        sesion.commit()


def estado(fabrica) -> dict[int, datetime.datetime | None]:
    """publicado_en de cada evento. SQLite no guarda la zona horaria: se la agrega."""
    with fabrica() as sesion:
        return {
            e.payload["numero"]: e.publicado_en and e.publicado_en.replace(tzinfo=datetime.UTC)
            for e in sesion.query(EventoSaliente)
        }


def publicar(fabrica, broker, lote=50) -> int:
    return asyncio.run(publicar_pendientes(fabrica, broker, lote=lote, ahora=lambda: PUBLICADO))


def test_publica_en_orden_de_creacion_y_marca_cada_uno(fabrica_sesiones):
    cargar_eventos(fabrica_sesiones, 3)
    broker = BrokerFalso()

    assert publicar(fabrica_sesiones, broker) == 3

    assert broker.publicados == [1, 2, 3]
    assert set(estado(fabrica_sesiones).values()) == {PUBLICADO}


def test_respeta_el_tamano_del_lote(fabrica_sesiones):
    cargar_eventos(fabrica_sesiones, 5)
    broker = BrokerFalso()

    assert publicar(fabrica_sesiones, broker, lote=2) == 2
    assert publicar(fabrica_sesiones, broker, lote=2) == 2

    assert broker.publicados == [1, 2, 3, 4]
    assert estado(fabrica_sesiones)[5] is None


def test_sin_confirmacion_no_marca_y_se_detiene(fabrica_sesiones):
    cargar_eventos(fabrica_sesiones, 3)
    broker = BrokerFalso(rechazar={2})

    with pytest.raises(RuntimeError, match="no confirmó"):
        publicar(fabrica_sesiones, broker)

    publicados = estado(fabrica_sesiones)
    assert publicados[1] == PUBLICADO
    assert publicados[2] is None  # no se marcó
    assert publicados[3] is None  # no se saltea: el orden se mantiene
    assert broker.publicados == [1]


def test_lo_no_confirmado_se_publica_en_el_proximo_intento(fabrica_sesiones):
    cargar_eventos(fabrica_sesiones, 3)
    broker = BrokerFalso(rechazar={2})
    with pytest.raises(RuntimeError):
        publicar(fabrica_sesiones, broker)

    broker.rechazar.clear()
    assert publicar(fabrica_sesiones, broker) == 2

    assert broker.publicados == [1, 2, 3]
    assert set(estado(fabrica_sesiones).values()) == {PUBLICADO}


def test_sin_pendientes_no_publica_nada(fabrica_sesiones):
    assert publicar(fabrica_sesiones, BrokerFalso()) == 0


class SesionQueSeCaeAlMarcar(Session):
    """Simula que el proceso muere después de la confirmación y antes del commit."""

    def commit(self):
        raise OperationalError("COMMIT", {}, Exception("el proceso se cayó"))


def test_si_se_cae_entre_publicar_y_marcar_se_vuelve_a_publicar(motor, fabrica_sesiones):
    cargar_eventos(fabrica_sesiones, 1)
    broker = BrokerFalso()
    fabrica_que_se_cae = sessionmaker(bind=motor, class_=SesionQueSeCaeAlMarcar)

    with pytest.raises(OperationalError):
        publicar(fabrica_que_se_cae, broker)
    assert broker.publicados == [1]
    assert estado(fabrica_sesiones)[1] is None  # confirmado por el broker, pero sin marcar

    # Al reiniciar, el evento sigue pendiente y se publica otra vez: el
    # consumidor lo descarta por id_evento ("al menos una vez").
    assert publicar(fabrica_sesiones, broker) == 1
    assert broker.publicados == [1, 1]
    assert estado(fabrica_sesiones)[1] == PUBLICADO
