from fastapi import FastAPI

from app.api import auth, perfiles

app = FastAPI(title="Servicio de Usuarios")
app.include_router(auth.router)
app.include_router(perfiles.router)


@app.get("/salud")
def salud():
    return {"estado": "ok", "servicio": "usuarios"}
