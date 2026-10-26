from fastapi import FastAPI

from app.api import turnos

app = FastAPI(title="Servicio de Reservas")
app.include_router(turnos.router)


@app.get("/salud")
def salud():
    return {"estado": "ok", "servicio": "reservas"}
