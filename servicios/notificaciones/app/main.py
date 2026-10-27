import asyncio

from fastapi import FastAPI

from app import consumidor

app = FastAPI(title="Servicio de Notificaciones")
_detener_consumidor = asyncio.Event()
_tarea_consumidor: asyncio.Task | None = None


@app.on_event("startup")
async def iniciar_consumidor() -> None:
    global _tarea_consumidor
    _detener_consumidor.clear()
    _tarea_consumidor = asyncio.create_task(
        consumidor.ejecutar_consumidor(_detener_consumidor)
    )


@app.on_event("shutdown")
async def detener_consumidor() -> None:
    _detener_consumidor.set()
    if _tarea_consumidor is not None:
        _tarea_consumidor.cancel()
        await asyncio.gather(_tarea_consumidor, return_exceptions=True)


@app.get("/salud")
def salud():
    return {"estado": "ok", "servicio": "notificaciones"}
