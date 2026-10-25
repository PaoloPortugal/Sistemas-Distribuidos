from fastapi import FastAPI

from app.api import interno

app = FastAPI(title="Servicio de Catálogo de médicos")
app.include_router(interno.router)


@app.get("/salud")
def salud():
    return {"estado": "ok", "servicio": "catalogo_medicos"}
