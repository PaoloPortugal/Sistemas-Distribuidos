import asyncio

from fastapi import FastAPI

from app import eventos

from app.api import turnos

app = FastAPI(title="Servicio de Reservas")
app.include_router(turnos.router)
_detener_publicador = asyncio.Event()
_tarea_publicador: asyncio.Task | None = None


@app.on_event("startup")
async def iniciar_publicador() -> None:
    global _tarea_publicador
    _detener_publicador.clear()
    _tarea_publicador = asyncio.create_task(eventos.ejecutar_publicador(_detener_publicador))


@app.on_event("shutdown")
async def detener_publicador() -> None:
    _detener_publicador.set()
    if _tarea_publicador is not None:
        await _tarea_publicador


@app.get("/salud")
def salud():
    return {"estado": "ok", "servicio": "reservas"}
