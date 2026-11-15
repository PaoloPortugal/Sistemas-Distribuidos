"""Observabilidad: logs JSON a stdout con correlation_id (docs/08-observabilidad.md).

Este archivo es idéntico en los cuatro servicios (usuarios, catalogo_medicos,
reservas y notificaciones); si se cambia, hay que cambiarlo en todos.

- `configurar_logs` deja una línea JSON por evento en stdout, también para los
  logs de uvicorn. Los campos pasados con `extra=` se agregan a la línea.
- `MiddlewareCorrelacion` toma el encabezado X-Correlation-ID del pedido (o
  genera un UUID), lo guarda en una variable de contexto, lo devuelve en la
  respuesta y registra el pedido con método, ruta, estado y duración.
- `obtener_correlation_id` / `con_correlation_id` permiten leerlo y fijarlo
  fuera de un pedido HTTP (clientes REST internos, publicador, consumidor).
"""

import contextlib
import contextvars
import datetime
import json
import logging
import re
import sys
import time
import uuid
from collections.abc import Iterator

ENCABEZADO = "X-Correlation-ID"
_ENCABEZADO_ASGI = ENCABEZADO.lower().encode("latin-1")
# Se acepta el identificador recibido solo si es razonable; si no, se genera uno.
_FORMATO_VALIDO = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
# Rutas que se registran en DEBUG para que los healthchecks no llenen los logs.
_RUTAS_SILENCIOSAS = {"/salud"}

_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)

registro = logging.getLogger("app.pedidos")


def obtener_correlation_id() -> str | None:
    return _correlation_id.get()


def nuevo_correlation_id() -> str:
    return str(uuid.uuid4())


@contextlib.contextmanager
def con_correlation_id(valor: str | None) -> Iterator[None]:
    """Fija el correlation_id mientras dura el bloque y después restaura el anterior."""
    token = _correlation_id.set(valor)
    try:
        yield
    finally:
        _correlation_id.reset(token)


def encabezados_correlacion() -> dict[str, str]:
    """Encabezado para reenviar el correlation_id en una llamada REST interna."""
    valor = obtener_correlation_id()
    return {ENCABEZADO: valor} if valor else {}


# Atributos propios de LogRecord: todo lo demás llegó por `extra=` y va a la línea JSON.
_ATRIBUTOS_DE_REGISTRO = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {
    "message",
    "asctime",
}


class FormateadorJson(logging.Formatter):
    def __init__(self, servicio: str):
        super().__init__()
        self._servicio = servicio

    def format(self, record: logging.LogRecord) -> str:
        datos = {
            "fecha": datetime.datetime.fromtimestamp(record.created, datetime.UTC).isoformat(),
            "nivel": record.levelname,
            "servicio": self._servicio,
            "logger": record.name,
            "mensaje": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", None) or obtener_correlation_id(),
        }
        for clave, valor in vars(record).items():
            if clave not in _ATRIBUTOS_DE_REGISTRO and clave not in datos:
                datos[clave] = valor
        if record.exc_info:
            datos["excepcion"] = self.formatException(record.exc_info)
        return json.dumps(datos, ensure_ascii=False, default=str)


class _ManejadorStdout(logging.StreamHandler):
    """Escribe en el sys.stdout vigente en cada evento (no en el del momento de crearlo)."""

    def __init__(self):
        super().__init__()

    @property
    def stream(self):
        return sys.stdout

    @stream.setter
    def stream(self, _valor):
        pass


def configurar_logs(servicio: str, nivel: str = "INFO") -> None:
    """Configura el logger raíz con una línea JSON por evento en stdout. Es idempotente."""
    raiz = logging.getLogger()
    for manejador in list(raiz.handlers):
        if isinstance(manejador, _ManejadorStdout):
            raiz.removeHandler(manejador)
    manejador = _ManejadorStdout()
    manejador.setFormatter(FormateadorJson(servicio))
    raiz.addHandler(manejador)
    raiz.setLevel(nivel.upper())
    # uvicorn instala sus propios manejadores de texto: se quitan para que sus
    # mensajes pasen por el raíz y salgan en JSON. El log de acceso lo reemplaza
    # el middleware (uvicorn corre con --no-access-log).
    for nombre in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(nombre)
        logger.handlers = []
        logger.propagate = True
    # httpx escribe una línea INFO por cada pedido de los clientes internos; el
    # middleware del servicio llamado ya registra cada pedido, así que solo se
    # dejan sus advertencias y errores.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _correlation_id_recibido(scope) -> str | None:
    for nombre, valor in scope.get("headers", []):
        if nombre == _ENCABEZADO_ASGI:
            texto = valor.decode("latin-1")
            return texto if _FORMATO_VALIDO.match(texto) else None
    return None


class MiddlewareCorrelacion:
    """Middleware ASGI: correlation_id por pedido y un log por pedido."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        valor = _correlation_id_recibido(scope) or nuevo_correlation_id()
        token = _correlation_id.set(valor)
        inicio = time.perf_counter()
        estado = 500

        async def enviar(mensaje):
            nonlocal estado
            if mensaje["type"] == "http.response.start":
                estado = mensaje["status"]
                encabezados = [
                    (nombre, contenido)
                    for nombre, contenido in mensaje.get("headers", [])
                    if nombre.lower() != _ENCABEZADO_ASGI
                ]
                encabezados.append((_ENCABEZADO_ASGI, valor.encode("latin-1")))
                mensaje = {**mensaje, "headers": encabezados}
            await send(mensaje)

        try:
            await self.app(scope, receive, enviar)
        except Exception:
            registro.exception("Error no controlado en %s %s", scope["method"], scope["path"])
            raise
        finally:
            nivel = logging.DEBUG if scope["path"] in _RUTAS_SILENCIOSAS else logging.INFO
            duracion_ms = round((time.perf_counter() - inicio) * 1000, 1)
            registro.log(
                nivel,
                "%s %s -> %d (%.1f ms)",
                scope["method"],
                scope["path"],
                estado,
                duracion_ms,
                extra={
                    "metodo": scope["method"],
                    "ruta": scope["path"],
                    "estado": estado,
                    "duracion_ms": duracion_ms,
                    "correlation_id": valor,
                },
            )
            _correlation_id.reset(token)
