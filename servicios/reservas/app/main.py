from fastapi import FastAPI

app = FastAPI(title="Servicio de Reservas")


@app.get("/salud")
def salud():
    return {"estado": "ok", "servicio": "reservas"}
