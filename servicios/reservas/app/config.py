from pydantic_settings import BaseSettings


class Configuracion(BaseSettings):
    nombre_servicio: str = "reservas"
    url_base_datos: str = ""
    nivel_log: str = "INFO"
    ruta_clave_publica_jwt: str = "/run/secrets/jwt_publica.pem"
    zona_horaria: str = "America/Montevideo"
    url_catalogo: str = ""
    timeout_catalogo_segundos: float = 3.0
    # Publicador del outbox (proceso aparte: python -m app.publicador).
    url_rabbitmq: str = ""
    publicador_lote: int = 50
    publicador_intervalo_segundos: float = 1.0
    publicador_espera_maxima_segundos: float = 30.0
    # Pausa entre eventos para limitar el ritmo; la prueba de fallos c) la usa
    # para poder matar al publicador a mitad de un lote.
    publicador_pausa_entre_eventos_segundos: float = 0.0


configuracion = Configuracion()
