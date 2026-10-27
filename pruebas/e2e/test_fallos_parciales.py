"""Fallos parciales (T21): eventos y mails sin pérdidas ni duplicados.

Corre contra el sistema levantado con Docker Compose; detiene y levanta
contenedores, así que tarda unos minutos:

    docker compose up -d --build
    pip install -r pruebas/requirements.txt
    pytest pruebas/e2e -v -s

a) notificaciones detenido: los eventos esperan en la cola y llegan al volver.
b) RabbitMQ detenido: el evento espera en el outbox y se publica al volver.
c) el publicador se cae a mitad de un lote, y un mismo mensaje se publica dos
   veces a mano: ningún mail duplicado.
d) Mailpit detenido: las NOTIFICACION quedan PENDIENTE y se envían al volver.

Cada prueba crea usuarios nuevos con el prefijo `fallo-<id>`.
"""

import datetime
import json
import os
import random
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest

BASE = os.environ.get("URL_GATEWAY", "http://localhost:8080")
USUARIOS = f"{BASE}/api/usuarios"
CATALOGO = f"{BASE}/api/catalogo-medicos"
RESERVAS = f"{BASE}/api/reservas"
MAILPIT = os.environ.get("URL_MAILPIT", "http://localhost:8025")
RABBITMQ = os.environ.get("URL_RABBITMQ_PANEL", "http://localhost:15672")
RAIZ_REPO = Path(__file__).resolve().parents[2]
CONTRASENA = "clave-segura-123"
SERVICIOS_DETENIBLES = ["rabbitmq", "mailpit", "notificaciones", "reservas-publicador"]


# --- Infraestructura ---------------------------------------------------------


def _sistema_levantado() -> bool:
    try:
        return all(
            httpx.get(f"{url}/salud", timeout=2).status_code == 200
            for url in (USUARIOS, CATALOGO, RESERVAS)
        ) and httpx.get(f"{MAILPIT}/api/v1/messages", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not _sistema_levantado(), reason="El sistema no está levantado (docker compose up)"
)


def compose(*argumentos: str, entorno: dict | None = None) -> None:
    subprocess.run(
        ["docker", "compose", *argumentos], cwd=RAIZ_REPO, check=True, capture_output=True,
        env=os.environ | (entorno or {}),
    )


def psql(consulta: str) -> str:
    resultado = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "sh", "-c",
         'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA'],
        input=consulta, capture_output=True, text=True, cwd=RAIZ_REPO, check=True,
    )
    return resultado.stdout.strip()


def esperar(condicion, *, segundos: float, descripcion: str, cada: float = 1.0):
    limite = time.monotonic() + segundos
    while True:
        try:
            valor = condicion()
        except (httpx.HTTPError, subprocess.CalledProcessError):
            valor = None
        if valor:
            return valor
        if time.monotonic() > limite:
            raise AssertionError(f"No pasó en {segundos:.0f} s: {descripcion}")
        time.sleep(cada)


def salud_de(servicio: str) -> str:
    resultado = subprocess.run(
        ["docker", "compose", "ps", servicio, "--format", "{{.Health}}"],
        cwd=RAIZ_REPO, capture_output=True, text=True, check=True,
    )
    return resultado.stdout.strip()


def todo_arriba() -> None:
    compose("start", *SERVICIOS_DETENIBLES)
    esperar(lambda: salud_de("rabbitmq") == "healthy", segundos=90, descripcion="RabbitMQ healthy")
    esperar(lambda: salud_de("notificaciones") == "healthy", segundos=90, descripcion="notificaciones healthy")
    esperar(
        lambda: httpx.get(f"{MAILPIT}/api/v1/messages", timeout=2).status_code == 200,
        segundos=60, descripcion="Mailpit responde",
    )


@pytest.fixture(autouse=True)
def servicios_arriba():
    """Cada prueba empieza y termina con todo levantado, aunque falle a la mitad."""
    todo_arriba()
    yield
    todo_arriba()


def credenciales_rabbitmq() -> tuple[str, str]:
    usuario = os.environ.get("RABBITMQ_USUARIO")
    contrasena = os.environ.get("RABBITMQ_CONTRASENA")
    if not (usuario and contrasena):
        valores = dict(
            linea.split("=", 1)
            for linea in (RAIZ_REPO / ".env").read_text(encoding="utf-8").splitlines()
            if "=" in linea and not linea.lstrip().startswith("#")
        )
        usuario, contrasena = valores["RABBITMQ_USUARIO"], valores["RABBITMQ_CONTRASENA"]
    return usuario, contrasena


def mensajes_en_cola(cola: str) -> int:
    respuesta = httpx.get(f"{RABBITMQ}/api/queues/%2F/{cola}", auth=credenciales_rabbitmq())
    return respuesta.json().get("messages", 0)


def mails_para(email: str) -> list[str]:
    """Asuntos de los mails que recibió `email` en Mailpit."""
    respuesta = httpx.get(
        f"{MAILPIT}/api/v1/search", params={"query": f'to:"{email}"', "limit": 500}, timeout=5
    )
    return [
        m["Subject"]
        for m in respuesta.json()["messages"]
        if any(d["Address"] == email for d in m["To"])
    ]


# --- Datos de prueba -----------------------------------------------------------


class Escenario:
    """Un profesional y un paciente nuevos, con sesión iniciada."""

    def __init__(self):
        corrida = uuid.uuid4().hex[:8]
        self.profesional = f"fallo-{corrida}-prof@ejemplo.com"
        self.paciente = f"fallo-{corrida}-pac@ejemplo.com"
        httpx.post(f"{USUARIOS}/registro/profesional", json={
            "email": self.profesional, "contrasena": CONTRASENA, "nombre": "Prueba",
            "apellido": "Fallos", "matricula": f"F-{corrida}", "id_especialidad": 1,
        }).raise_for_status()
        httpx.post(f"{USUARIOS}/registro/paciente", json={
            "email": self.paciente, "contrasena": CONTRASENA, "nombre": "Paciente",
            "apellido": "Fallos", "documento": f"F{corrida}",
        }).raise_for_status()
        self.como_profesional = self._login(self.profesional)
        self.como_paciente = self._login(self.paciente)
        self.dia = datetime.date.today() + datetime.timedelta(days=3)

    @staticmethod
    def _login(email: str) -> dict:
        respuesta = httpx.post(f"{USUARIOS}/login", json={"email": email, "contrasena": CONTRASENA})
        respuesta.raise_for_status()
        return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}

    def reservar(self, cantidad: int) -> list[int]:
        """Crea `cantidad` franjas de 30 minutos y las reserva; devuelve los id_turno."""
        turnos = []
        with httpx.Client(timeout=15) as cliente:
            for i in range(cantidad):
                inicio = datetime.datetime.combine(self.dia, datetime.time(7, 0)) + datetime.timedelta(minutes=30 * i)
                franja = cliente.post(f"{CATALOGO}/disponibilidades", headers=self.como_profesional, json={
                    "fecha": inicio.date().isoformat(),
                    "horario_inicio": inicio.strftime("%H:%M"),
                    "horario_fin": (inicio + datetime.timedelta(minutes=30)).strftime("%H:%M"),
                })
                franja.raise_for_status()
                turno = cliente.post(f"{RESERVAS}/turnos", headers=self.como_paciente, json={
                    "id_disponibilidad": franja.json()["id_disponibilidad"], "id_servicio": 1,
                })
                turno.raise_for_status()
                turnos.append(turno.json()["id_turno"])
        return turnos


def pendientes_en_outbox(turnos: list[int]) -> int:
    ids = ",".join(f"'{t}'" for t in turnos)
    return int(psql(
        "SELECT count(*) FROM reservas.evento_saliente "
        f"WHERE publicado_en IS NULL AND payload->>'id_turno' IN ({ids})"
    ))


def notificaciones_de(turnos: list[int]) -> list[tuple]:
    ids = ",".join(str(t) for t in turnos)
    filas = psql(
        "SELECT n.id_turno, n.destinatario, n.estado_notificacion, e.intentos "
        "FROM notificaciones.notificacion n JOIN notificaciones.envio_mail e USING (id_notificacion) "
        f"WHERE n.id_turno IN ({ids}) ORDER BY 1, 2"
    )
    return [tuple(f.split("|")) for f in filas.splitlines() if f]


def sin_duplicados(asuntos: list[str]) -> bool:
    return len(asuntos) == len(set(asuntos))


# --- a) notificaciones detenido -------------------------------------------------


def test_a_notificaciones_detenido_los_mails_llegan_al_volver():
    escenario = Escenario()
    compose("stop", "notificaciones")

    turnos = escenario.reservar(3)

    esperar(lambda: pendientes_en_outbox(turnos) == 0, segundos=30, descripcion="eventos publicados")
    esperar(lambda: mensajes_en_cola("notificaciones.turnos") >= 3, segundos=30,
            descripcion="3 mensajes esperando en la cola")
    print(f"\n  a) con notificaciones detenido: {mensajes_en_cola('notificaciones.turnos')} "
          "mensajes esperando en la cola, 0 mails")
    assert mails_para(escenario.paciente) == []

    compose("start", "notificaciones")

    esperar(lambda: len(mails_para(escenario.paciente)) >= 3 and len(mails_para(escenario.profesional)) >= 3,
            segundos=90, descripcion="6 mails en Mailpit")
    time.sleep(5)  # por si llegara algún duplicado tarde
    al_paciente, al_profesional = mails_para(escenario.paciente), mails_para(escenario.profesional)
    print(f"  a) mails: {len(al_paciente)} al paciente, {len(al_profesional)} al profesional")
    assert len(al_paciente) == 3 and sin_duplicados(al_paciente)
    assert len(al_profesional) == 3 and sin_duplicados(al_profesional)
    assert {f[2] for f in notificaciones_de(turnos)} == {"ENVIADO"}
    assert len(notificaciones_de(turnos)) == 6


# --- b) RabbitMQ detenido --------------------------------------------------------


def test_b_rabbitmq_detenido_el_evento_espera_en_el_outbox():
    escenario = Escenario()
    compose("stop", "rabbitmq")

    turnos = escenario.reservar(1)  # reservar no depende de RabbitMQ

    time.sleep(5)
    assert pendientes_en_outbox(turnos) == 1  # publicado_en sigue nulo
    print("\n  b) con RabbitMQ detenido: el evento sigue en el outbox con publicado_en nulo")

    compose("start", "rabbitmq")

    esperar(lambda: pendientes_en_outbox(turnos) == 0, segundos=120, descripcion="evento publicado")
    esperar(lambda: len(mails_para(escenario.paciente)) == 1 and len(mails_para(escenario.profesional)) == 1,
            segundos=90, descripcion="2 mails en Mailpit")
    time.sleep(3)
    assert len(mails_para(escenario.paciente)) == 1
    assert len(mails_para(escenario.profesional)) == 1
    print("  b) al volver RabbitMQ: evento publicado y 2 mails entregados")


# --- c) publicador caído a mitad de lote, y mensaje duplicado a mano ---------------


def test_c_publicador_caido_a_mitad_de_lote_sin_mails_duplicados():
    escenario = Escenario()
    compose("stop", "reservas-publicador")
    turnos = escenario.reservar(30)
    assert pendientes_en_outbox(turnos) == 30

    # Sin pausa, el publicador manda los 30 en milisegundos y no se lo puede
    # matar a la mitad: se lo recrea publicando un evento cada 0,2 s.
    lento = {"PUBLICADOR_PAUSA_ENTRE_EVENTOS_SEGUNDOS": "0.2"}
    try:
        compose("up", "-d", "--no-deps", "--force-recreate", "reservas-publicador", entorno=lento)
        esperar(lambda: 5 <= 30 - pendientes_en_outbox(turnos) <= 25, segundos=60, cada=0.1,
                descripcion="el publicador va por la mitad del lote")
        compose("kill", "reservas-publicador")  # SIGKILL: se cae, no se detiene ordenadamente
        publicados = 30 - pendientes_en_outbox(turnos)
        print(f"\n  c) publicador matado con {publicados} de 30 eventos publicados")
        assert 0 < publicados < 30
        time.sleep(3)
        assert 30 - pendientes_en_outbox(turnos) == publicados  # nadie publica mientras está caído
    finally:
        compose("up", "-d", "--no-deps", "--force-recreate", "reservas-publicador",
                entorno={"PUBLICADOR_PAUSA_ENTRE_EVENTOS_SEGUNDOS": "0"})

    esperar(lambda: pendientes_en_outbox(turnos) == 0, segundos=60, descripcion="lote completo")
    esperar(lambda: len(mails_para(escenario.paciente)) >= 30 and len(mails_para(escenario.profesional)) >= 30,
            segundos=120, descripcion="60 mails en Mailpit")
    time.sleep(5)
    al_paciente, al_profesional = mails_para(escenario.paciente), mails_para(escenario.profesional)
    print(f"  c) al volver el publicador: {len(al_paciente)} mails al paciente y "
          f"{len(al_profesional)} al profesional, sin repetidos")
    assert len(al_paciente) == 30 and sin_duplicados(al_paciente)
    assert len(al_profesional) == 30 and sin_duplicados(al_profesional)


def test_c_el_mismo_mensaje_publicado_dos_veces_genera_solo_dos_mails():
    corrida = uuid.uuid4().hex[:8]
    paciente, profesional = f"dup-{corrida}-pac@ejemplo.com", f"dup-{corrida}-prof@ejemplo.com"
    id_turno = random.randint(900_000, 999_999)  # turno inventado: no hace falta que exista
    evento = {
        "id_evento": str(uuid.uuid4()), "tipo": "turno.confirmado",
        "ocurrido_en": datetime.datetime.now(datetime.UTC).isoformat(),
        "id_turno": id_turno, "id_disponibilidad": 1, "id_servicio": 1,
        "email_paciente": paciente, "email_profesional": profesional,
        "fecha": "2026-12-01", "horario_inicio": "10:00:00", "horario_fin": "10:30:00",
    }
    pedido = {
        "properties": {"message_id": evento["id_evento"], "delivery_mode": 2,
                       "content_type": "application/json"},
        "routing_key": "turno.confirmado",
        "payload": json.dumps(evento),
        "payload_encoding": "string",
    }

    for _ in range(2):
        respuesta = httpx.post(f"{RABBITMQ}/api/exchanges/%2F/turnos/publish",
                               json=pedido, auth=credenciales_rabbitmq())
        assert respuesta.json() == {"routed": True}

    esperar(lambda: len(mails_para(paciente)) >= 1 and len(mails_para(profesional)) >= 1,
            segundos=60, descripcion="mails del evento")
    time.sleep(5)
    print(f"\n  c) mismo mensaje publicado 2 veces: {len(mails_para(paciente))} mail al paciente, "
          f"{len(mails_para(profesional))} al profesional")
    assert len(mails_para(paciente)) == 1
    assert len(mails_para(profesional)) == 1
    assert psql(f"SELECT count(*) FROM notificaciones.evento_procesado "
                f"WHERE id_evento = '{evento['id_evento']}'") == "1"
    assert len(notificaciones_de([id_turno])) == 2


# --- d) Mailpit detenido ---------------------------------------------------------


def test_d_mailpit_detenido_las_notificaciones_esperan_pendientes():
    escenario = Escenario()
    compose("stop", "mailpit")

    turnos = escenario.reservar(1)

    def pendientes_con_reintentos():
        filas = notificaciones_de(turnos)
        return len(filas) == 2 and all(f[2] == "PENDIENTE" and int(f[3]) >= 2 for f in filas) and filas

    filas = esperar(pendientes_con_reintentos, segundos=90, descripcion="2 PENDIENTE con reintentos")
    print(f"\n  d) con Mailpit detenido: {[(f[1], f[2], f'intentos={f[3]}') for f in filas]}")

    compose("start", "mailpit")

    esperar(lambda: {f[2] for f in notificaciones_de(turnos)} == {"ENVIADO"}, segundos=120,
            descripcion="las 2 notificaciones ENVIADO")
    print(f"  d) al volver Mailpit: {[(f[1], f[2], f'intentos={f[3]}') for f in notificaciones_de(turnos)]}")
    assert len(mails_para(escenario.paciente)) == 1
    assert len(mails_para(escenario.profesional)) == 1
