from fastapi import FastAPI

app = FastAPI(title="Servicio de Usuarios")


@app.get("/salud")
def salud():
    return {"estado": "ok", "servicio": "usuarios"}
