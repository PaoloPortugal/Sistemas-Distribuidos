"""Reservar contra borrar: el profesional borra un horario mientras 5 pacientes lo reservan.

Corre contra el sistema levantado con Docker Compose, a través de Traefik:

    docker compose up -d --build
    pip install -r pruebas/requirements.txt
    pytest pruebas/concurrencia -v

En cada una de las 20 rondas sale una de dos, nunca una mezcla (ADR 003):
- el borrado gana (204): ningún paciente consiguió turno y no queda ningún
  turno RESERVADO sobre ese horario;
- una reserva gana (201): el borrado responde 409, el horario sigue en
  catálogo y hay exactamente un turno RESERVADO.
Lo garantizan el bloqueo en reservas y el lock de PostgreSQL entre bloquear y
reservar.

Usa el prefijo `conc-<id>`, igual que test_doble_reserva.py (mismo borrado).
"""

import datetime
import os
import subprocess
import threading
import uuid
from pathlib import Path

import httpx
import pytest

BASE = os.environ.get("URL_GATEWAY", "http://localhost:8080")
USUARIOS = f"{BASE}/api/usuarios"
CATALOGO = f"{BASE}/api/catalogo-medicos"
RESERVAS = f"{BASE}/api/reservas"
RAIZ_REPO = Path(__file__).resolve().parents[2]
CONTRASENA = "clave-segura-123"
PACIENTES = 5
RONDAS = 20


def _sistema_levantado() -> bool:
    try:
        return all(
            httpx.get(f"{url}/salud", timeout=2).status_code == 200
            for url in (USUARIOS, CATALOGO, RESERVAS)
        )
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not _sistema_levantado(), reason="El sistema no está levantado (docker compose up)"
)


def _login(email: str) -> dict:
    respuesta = httpx.post(f"{USUARIOS}/login", json={"email": email, "contrasena": CONTRASENA})
    respuesta.raise_for_status()
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


def _psql(consulta: str) -> str:
    """Consulta la base del stack como superusuario, dentro del contenedor."""
    resultado = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "sh", "-c",
         'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA'],
        input=consulta,
        capture_output=True,
        text=True,
        cwd=RAIZ_REPO,
        check=True,
    )
    return resultado.stdout.strip()


@pytest.fixture(scope="module")
def escenario() -> dict:
    """Un profesional y cinco pacientes con sesión."""
    corrida = uuid.uuid4().hex[:8]
    profesional = f"conc-{corrida}-prof@ejemplo.com"
    httpx.post(
        f"{USUARIOS}/registro/profesional",
        json={
            "email": profesional,
            "contrasena": CONTRASENA,
            "nombre": "Prueba",
            "apellido": "Borrado",
            "matricula": f"CONC-{corrida}",
            "id_especialidad": 1,
        },
    ).raise_for_status()

    pacientes = []
    for i in range(PACIENTES):
        email = f"conc-{corrida}-pac{i}@ejemplo.com"
        httpx.post(
            f"{USUARIOS}/registro/paciente",
            json={
                "email": email,
                "contrasena": CONTRASENA,
                "nombre": "Paciente",
                "apellido": f"N{i}",
                "documento": f"B{corrida}{i}",
            },
        ).raise_for_status()
        pacientes.append(_login(email))

    return {"como_profesional": _login(profesional), "pacientes": pacientes}


def _crear_franja(como_profesional: dict, ronda: int) -> int:
    """Una franja de 30 minutos por ronda, pasado mañana desde las 8:00."""
    fecha = datetime.date.today() + datetime.timedelta(days=2)
    inicio = datetime.datetime.combine(fecha, datetime.time(8, 0)) + datetime.timedelta(
        minutes=30 * ronda
    )
    fin = inicio + datetime.timedelta(minutes=30)
    respuesta = httpx.post(
        f"{CATALOGO}/disponibilidades",
        json={
            "fecha": fecha.isoformat(),
            "horario_inicio": inicio.strftime("%H:%M"),
            "horario_fin": fin.strftime("%H:%M"),
        },
        headers=como_profesional,
    )
    respuesta.raise_for_status()
    return respuesta.json()["id_disponibilidad"]


def _ronda(escenario: dict, id_disponibilidad: int) -> tuple[int, list[int]]:
    """Borrado y reservas salen juntos; devuelve el código del borrado y los de las reservas."""
    barrera = threading.Barrier(PACIENTES + 1)
    codigos_reserva: list[int] = []
    codigo_borrado: list[int] = []
    cerrojo = threading.Lock()

    def reservar(encabezados: dict) -> None:
        with httpx.Client(timeout=15) as cliente:
            barrera.wait()
            respuesta = cliente.post(
                f"{RESERVAS}/turnos",
                json={"id_disponibilidad": id_disponibilidad, "id_servicio": 1},
                headers=encabezados,
            )
        with cerrojo:
            codigos_reserva.append(respuesta.status_code)

    def borrar() -> None:
        with httpx.Client(timeout=15) as cliente:
            barrera.wait()
            respuesta = cliente.delete(
                f"{CATALOGO}/disponibilidades/{id_disponibilidad}",
                headers=escenario["como_profesional"],
            )
        codigo_borrado.append(respuesta.status_code)

    hilos = [threading.Thread(target=reservar, args=(e,)) for e in escenario["pacientes"]]
    hilos.append(threading.Thread(target=borrar))
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    return codigo_borrado[0], sorted(codigos_reserva)


def test_reservar_contra_borrar(escenario):
    ganadores = {"borrado": 0, "reserva": 0}

    for ronda in range(RONDAS):
        id_disponibilidad = _crear_franja(escenario["como_profesional"], ronda)

        borrado, reservas = _ronda(escenario, id_disponibilidad)

        reservados = _psql(
            f"SELECT count(*) FROM reservas.turno "
            f"WHERE id_disponibilidad = {id_disponibilidad} AND estado = 'RESERVADO'"
        )
        en_catalogo = _psql(
            f"SELECT count(*) FROM catalogo_medicos.disponibilidad "
            f"WHERE id_disponibilidad = {id_disponibilidad}"
        )
        detalle = f"ronda {ronda}: borrado={borrado} reservas={reservas}"
        if borrado == 204:
            ganadores["borrado"] += 1
            # Las reservas chocan con el bloqueo (409) o ya no encuentran la franja (404).
            assert all(c in (404, 409) for c in reservas), detalle
            assert (reservados, en_catalogo) == ("0", "0"), detalle
        else:
            ganadores["reserva"] += 1
            assert borrado == 409, detalle
            assert reservas == [201] + [409] * (PACIENTES - 1), detalle
            assert (reservados, en_catalogo) == ("1", "1"), detalle

    print(f"\n{RONDAS} rondas: ganó el borrado {ganadores['borrado']}, "
          f"ganó una reserva {ganadores['reserva']}")
