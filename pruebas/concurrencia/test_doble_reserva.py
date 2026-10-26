"""Doble reserva: 10 pacientes reservan el mismo horario al mismo tiempo.

Corre contra el sistema levantado con Docker Compose, a través de Traefik:

    docker compose up -d --build
    pip install -r pruebas/requirements.txt
    pytest pruebas/concurrencia -v

Espera exactamente un 201 y nueve 409, y que en la base quede un solo turno
RESERVADO (y un solo evento turno.confirmado en el outbox) para esa franja.
Lo decide el índice único parcial de PostgreSQL, no una consulta previa.

Cada corrida crea usuarios nuevos con el prefijo `conc-<id>`. Para borrarlos:

    DELETE FROM reservas.evento_saliente WHERE payload->>'email_profesional' LIKE 'conc-%';
    DELETE FROM reservas.turno WHERE email_profesional LIKE 'conc-%';
    DELETE FROM catalogo_medicos.disponibilidad WHERE email_profesional LIKE 'conc-%';
    DELETE FROM catalogo_medicos.profesional WHERE email LIKE 'conc-%';
    DELETE FROM usuarios.usuario WHERE email LIKE 'conc-%';
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
PACIENTES = 10


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
    """Un profesional con una franja para mañana y diez pacientes con sesión."""
    corrida = uuid.uuid4().hex[:8]
    profesional = f"conc-{corrida}-prof@ejemplo.com"
    httpx.post(
        f"{USUARIOS}/registro/profesional",
        json={
            "email": profesional,
            "contrasena": CONTRASENA,
            "nombre": "Prueba",
            "apellido": "Concurrencia",
            "matricula": f"CONC-{corrida}",
            "id_especialidad": 1,
        },
    ).raise_for_status()
    como_profesional = _login(profesional)

    manana = datetime.date.today() + datetime.timedelta(days=2)
    franja = httpx.post(
        f"{CATALOGO}/disponibilidades",
        json={"fecha": manana.isoformat(), "horario_inicio": "10:00", "horario_fin": "10:30"},
        headers=como_profesional,
    )
    franja.raise_for_status()

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
                "documento": f"C{corrida}{i}",
            },
        ).raise_for_status()
        pacientes.append(_login(email))

    return {
        "id_disponibilidad": franja.json()["id_disponibilidad"],
        "como_profesional": como_profesional,
        "pacientes": pacientes,
    }


def test_diez_pacientes_reservan_el_mismo_horario(escenario):
    id_disponibilidad = escenario["id_disponibilidad"]
    barrera = threading.Barrier(PACIENTES)
    codigos: list[int] = []
    cerrojo = threading.Lock()

    def reservar(encabezados: dict) -> None:
        with httpx.Client(timeout=15) as cliente:
            barrera.wait()  # salen todos juntos
            respuesta = cliente.post(
                f"{RESERVAS}/turnos",
                json={"id_disponibilidad": id_disponibilidad, "id_servicio": 1},
                headers=encabezados,
            )
        with cerrojo:
            codigos.append(respuesta.status_code)

    hilos = [threading.Thread(target=reservar, args=(e,)) for e in escenario["pacientes"]]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert sorted(codigos) == [201] + [409] * (PACIENTES - 1), codigos

    # En la base: un solo turno RESERVADO y un solo evento para esa franja.
    reservados = _psql(
        f"SELECT count(*) FROM reservas.turno "
        f"WHERE id_disponibilidad = {id_disponibilidad} AND estado = 'RESERVADO'"
    )
    eventos = _psql(
        f"SELECT count(*) FROM reservas.evento_saliente "
        f"WHERE tipo = 'turno.confirmado' "
        f"AND (payload->>'id_disponibilidad')::int = {id_disponibilidad}"
    )
    assert (reservados, eventos) == ("1", "1")

    # Y el profesional lo ve una sola vez en su agenda.
    agenda = httpx.get(
        f"{RESERVAS}/agenda", headers=escenario["como_profesional"],
        params={"desde": datetime.date.today().isoformat()},
    ).json()
    assert [t["id_disponibilidad"] for t in agenda] == [id_disponibilidad]
