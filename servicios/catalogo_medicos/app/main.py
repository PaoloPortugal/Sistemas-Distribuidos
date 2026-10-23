from fastapi import FastAPI

app = FastAPI(title="Servicio de Catálogo de médicos")


@app.get("/salud")
def salud():
    return {"estado": "ok", "servicio": "catalogo_medicos"}
