from pydantic_settings import BaseSettings


class Configuracion(BaseSettings):
    nombre_servicio: str = "notificaciones"
    url_base_datos: str = ""
    nivel_log: str = "INFO"


configuracion = Configuracion()
