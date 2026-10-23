from fastapi import FastAPI

app = FastAPI(title="Servicio de Notificaciones")


@app.get("/salud")
def salud():
    return {"estado": "ok", "servicio": "notificaciones"}
