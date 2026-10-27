from pydantic_settings import BaseSettings


class Configuracion(BaseSettings):
    nombre_servicio: str = "notificaciones"
    url_base_datos: str = ""
    nivel_log: str = "INFO"
    # Consumidor (ADR 008)
    url_rabbitmq: str = ""
    prefetch: int = 10
    limite_entregas: int = 5  # x-delivery-limit de la cola quorum
    # Envío de mails (ADR 008)
    smtp_host: str = "mailpit"
    smtp_puerto: int = 1025
    smtp_remitente: str = "turnos@clinica.local"
    smtp_timeout_segundos: float = 10.0
    max_intentos_envio: int = 8
    espera_minima_segundos: float = 5.0
    espera_maxima_segundos: float = 60.0
    envio_intervalo_segundos: float = 2.0
    # En los tests la API se levanta sin el consumidor ni el envío.
    iniciar_procesos: bool = True


configuracion = Configuracion()
