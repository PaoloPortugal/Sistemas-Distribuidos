from fastapi import FastAPI

from app.api import interno, turnos

app = FastAPI(title="Servicio de Reservas")
app.include_router(turnos.router)
app.include_router(interno.router)


@app.get("/salud")
def salud():
    return {"estado": "ok", "servicio": "reservas"}
