from fastapi import FastAPI

from app.api import disponibilidad, interno, medicos
from app.config import configuracion
from app.observabilidad import MiddlewareCorrelacion, configurar_logs

configurar_logs(configuracion.nombre_servicio, configuracion.nivel_log)

app = FastAPI(title="Servicio de Catálogo de médicos")
app.add_middleware(MiddlewareCorrelacion)
app.include_router(medicos.router)
app.include_router(disponibilidad.router)
app.include_router(interno.router)


@app.get("/salud")
def salud():
    return {"estado": "ok", "servicio": "catalogo_medicos"}
