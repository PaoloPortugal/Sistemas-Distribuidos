from pydantic_settings import BaseSettings


class Configuracion(BaseSettings):
    nombre_servicio: str = "usuarios"
    url_base_datos: str = ""
    nivel_log: str = "INFO"
    ruta_clave_privada_jwt: str = "/run/secrets/jwt_privada.pem"
    ruta_clave_publica_jwt: str = "/run/secrets/jwt_publica.pem"
    duracion_token_minutos: int = 60
    url_catalogo: str = ""
    timeout_catalogo_segundos: float = 3.0


configuracion = Configuracion()
