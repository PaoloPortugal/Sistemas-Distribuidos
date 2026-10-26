from pydantic_settings import BaseSettings


class Configuracion(BaseSettings):
    nombre_servicio: str = "catalogo_medicos"
    url_base_datos: str = ""
    nivel_log: str = "INFO"
    ruta_clave_publica_jwt: str = "/run/secrets/jwt_publica.pem"
    zona_horaria: str = "America/Montevideo"


configuracion = Configuracion()
