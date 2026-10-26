from fastapi import FastAPI

from app.api import disponibilidad, interno, medicos

app = FastAPI(title="Servicio de Catálogo de médicos")
app.include_router(medicos.router)
app.include_router(disponibilidad.router)
app.include_router(interno.router)


@app.get("/salud")
def salud():
    return {"estado": "ok", "servicio": "catalogo_medicos"}
