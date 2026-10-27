#!/usr/bin/env python3
"""Crea profesionales y disponibilidades para la demo local.

Usa las APIs publicadas por el gateway para respetar los limites entre
servicios. Es idempotente para los datos que ya existan: ante un 409 intenta
iniciar sesion con el profesional y continua creando sus disponibilidades.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = os.getenv("BASE_URL", "http://localhost:8080").rstrip("/")
CONTRASENA = os.getenv("DEMO_CONTRASENA", "DemoTurnos2026!")


@dataclass(frozen=True)
class ProfesionalDemo:
    email: str
    nombre: str
    apellido: str
    matricula: str
    id_especialidad: int


PROFESIONALES = (
    ProfesionalDemo("sofia.garcia.demo@example.com", "Sofia", "Garcia", "DEMO-CLIN-001", 1),
    ProfesionalDemo("mateo.rodriguez.demo@example.com", "Mateo", "Rodriguez", "DEMO-PED-001", 2),
    ProfesionalDemo("valentina.silva.demo@example.com", "Valentina", "Silva", "DEMO-CARD-001", 3),
    ProfesionalDemo("lucas.fernandez.demo@example.com", "Lucas", "Fernandez", "DEMO-DERM-001", 4),
    ProfesionalDemo("camila.pereira.demo@example.com", "Camila", "Pereira", "DEMO-CLIN-002", 1),
)


def pedir(ruta: str, metodo: str = "GET", cuerpo: dict | None = None, token: str | None = None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    cabeceras = {"Accept": "application/json"}
    if cuerpo is not None:
        cabeceras["Content-Type"] = "application/json"
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    solicitud = Request(f"{BASE_URL}{ruta}", data=datos, headers=cabeceras, method=metodo)
    try:
        with urlopen(solicitud, timeout=15) as respuesta:
            contenido = respuesta.read()
            return respuesta.status, json.loads(contenido) if contenido else None
    except HTTPError as error:
        contenido = error.read()
        try:
            detalle = json.loads(contenido)
        except json.JSONDecodeError:
            detalle = {"detail": contenido.decode(errors="replace")}
        return error.code, detalle
    except URLError as error:
        raise RuntimeError(f"No se pudo conectar con {BASE_URL}: {error.reason}") from error


def registrar(profesional: ProfesionalDemo) -> None:
    datos = {
        "email": profesional.email,
        "contrasena": CONTRASENA,
        "nombre": profesional.nombre,
        "apellido": profesional.apellido,
        "matricula": profesional.matricula,
        "id_especialidad": profesional.id_especialidad,
    }
    estado, cuerpo = pedir("/api/usuarios/registro/profesional", "POST", datos)
    if estado == 201:
        print(f"  Profesional creado: Dr. {profesional.nombre} {profesional.apellido}")
    elif estado == 409:
        print(f"  Ya existia: Dr. {profesional.nombre} {profesional.apellido}")
    else:
        raise RuntimeError(f"No se pudo registrar {profesional.email}: {estado} {cuerpo}")


def iniciar_sesion(email: str) -> str:
    estado, cuerpo = pedir(
        "/api/usuarios/login",
        "POST",
        {"email": email, "contrasena": CONTRASENA},
    )
    if estado != 200:
        raise RuntimeError(f"No se pudo iniciar sesion como {email}: {estado} {cuerpo}")
    return cuerpo["access_token"]


def dias_de_demo(cantidad: int = 7) -> list[dt.date]:
    dias = []
    candidato = dt.date.today() + dt.timedelta(days=1)
    while len(dias) < cantidad:
        if candidato.weekday() < 5:
            dias.append(candidato)
        candidato += dt.timedelta(days=1)
    return dias


def crear_disponibilidades(profesional: ProfesionalDemo, token: str) -> int:
    creadas = 0
    for fecha in dias_de_demo():
        for inicio, fin in (("09:00:00", "09:30:00"), ("11:00:00", "11:30:00"), ("15:00:00", "15:30:00")):
            estado, cuerpo = pedir(
                "/api/catalogo-medicos/disponibilidades",
                "POST",
                {"fecha": fecha.isoformat(), "horario_inicio": inicio, "horario_fin": fin},
                token,
            )
            if estado == 201:
                creadas += 1
            elif estado != 409:
                raise RuntimeError(
                    f"No se pudo crear disponibilidad para {profesional.email}: "
                    f"{estado} {cuerpo}"
                )
    return creadas


def main() -> int:
    print(f"Gateway: {BASE_URL}")
    print(f"Contrasena de demo: {CONTRASENA}")
    print("Creando profesionales y horarios...")
    try:
        for profesional in PROFESIONALES:
            registrar(profesional)
            token = iniciar_sesion(profesional.email)
            creadas = crear_disponibilidades(profesional, token)
            print(f"  Disponibilidades nuevas: {creadas}")
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Datos de demo listos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
