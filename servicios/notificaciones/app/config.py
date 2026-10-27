from pydantic_settings import BaseSettings


class Configuracion(BaseSettings):
    nombre_servicio: str = "notificaciones"
    url_base_datos: str = ""
    nivel_log: str = "INFO"
    url_rabbitmq: str = ""
    smtp_host: str = "localhost"
    smtp_puerto: int = 1025
    max_reintentos: int = 5


configuracion = Configuracion()
