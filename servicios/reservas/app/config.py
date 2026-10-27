from pydantic_settings import BaseSettings


class Configuracion(BaseSettings):
    nombre_servicio: str = "reservas"
    url_base_datos: str = ""
    nivel_log: str = "INFO"
    ruta_clave_publica_jwt: str = "/run/secrets/jwt_publica.pem"
    zona_horaria: str = "America/Montevideo"
    url_catalogo: str = ""
    timeout_catalogo_segundos: float = 3.0
    url_rabbitmq: str = ""
    intervalo_publicador_segundos: float = 1.0


configuracion = Configuracion()
