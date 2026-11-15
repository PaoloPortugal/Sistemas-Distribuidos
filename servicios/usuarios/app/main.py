from fastapi import FastAPI

from app.api import auth, interno, perfiles
from app.config import configuracion
from app.observabilidad import MiddlewareCorrelacion, configurar_logs

configurar_logs(configuracion.nombre_servicio, configuracion.nivel_log)

app = FastAPI(title="Servicio de Usuarios")
app.add_middleware(MiddlewareCorrelacion)
app.include_router(auth.router)
app.include_router(perfiles.router)
app.include_router(interno.router)


@app.get("/salud")
def salud():
    return {"estado": "ok", "servicio": "usuarios"}
