# Observabilidad

De los tres pilares de la observabilidad (logs, métricas y trazas) se
implementó **el de logs**. Un pedido pasa por varios servicios y por
RabbitMQ; cuando algo falla, lo primero que hace falta es poder seguirlo de
punta a punta. Para eso alcanza con logs estructurados que lleven un
identificador común, el `correlation_id`. Métricas y trazas distribuidas
(por ejemplo con Prometheus u OpenTelemetry) no están implementadas.

Todo se configura en un único módulo, `app/observabilidad.py`, que es
**idéntico en los cuatro servicios**. Si se cambia, hay que cambiarlo en
todos; `tests/test_observabilidad.py` también es el mismo en los cuatro.

## Logs JSON a stdout

Cada servicio escribe **una línea JSON por evento en stdout**, sin archivos
(factor XI, [doce factores](07-doce-factores.md)). Docker guarda esa salida y
se consulta con `docker compose logs`.

| Campo | Contenido |
| --- | --- |
| `fecha` | Fecha y hora del evento, en UTC (ISO 8601). |
| `nivel` | `DEBUG`, `INFO`, `WARNING` o `ERROR`. |
| `servicio` | `usuarios`, `catalogo_medicos`, `reservas`, `reservas-publicador` o `notificaciones` (variable `NOMBRE_SERVICIO`). |
| `logger` | Módulo que escribió la línea, por ejemplo `app.dominio.turnos`. |
| `mensaje` | Texto legible del evento. |
| `correlation_id` | Identificador del pedido que originó el evento; `null` si no hay ninguno (arranque, ciclo de envío). |
| `excepcion` | Traza de la excepción, solo en los errores no controlados. |

A estos campos se suman los propios de cada evento (los que el código pasa
con `extra=`): ids, motivos de rechazo, duración del pedido, etc. Un ejemplo:

```json
{"fecha": "2026-11-02T13:00:01.204+00:00", "nivel": "INFO", "servicio": "reservas", "logger": "app.dominio.turnos", "mensaje": "Turno 15 reservado", "correlation_id": "6f1c2a9e-1b7d-4c55-9a43-0d2f8e7b5a10", "id_turno": 15, "id_disponibilidad": 7, "id_servicio": 1}
```

También pasan por el mismo formato los logs de uvicorn, los de las librerías
(por ejemplo aio-pika) y las advertencias de Python (logger `py.warnings`).
Las únicas líneas en texto son las de Alembic, que corre las migraciones
antes de arrancar la aplicación.

El log de acceso de uvicorn está desactivado porque lo reemplaza el del
middleware, que incluye el `correlation_id`. No alcanza con `--no-access-log`
(en los Dockerfile): uvicorn lo escribe igual si el logger `uvicorn.access`
hereda el manejador del raíz, así que `configurar_logs` le corta la
propagación. Los logs de `httpx`, la librería de los clientes REST internos,
se dejan solo desde `WARNING`: cada llamada interna ya queda registrada por
el middleware del servicio llamado.

El nivel mínimo se elige con la variable de entorno `NIVEL_LOG` (por defecto
`INFO`). En `INFO`, `/salud` no aparece: se registra en `DEBUG` para que los
healthchecks no llenen los logs.

## Identificador de correlación

### En cada pedido HTTP

`MiddlewareCorrelacion` (un middleware ASGI) toma el encabezado
`X-Correlation-ID` del pedido. Si no llega, o no tiene un formato razonable
(letras, dígitos y `. _ : -`, hasta 128 caracteres), genera un UUID. El valor:

- se guarda en una variable de contexto (`contextvars`), de donde lo toma el
  formateador para todas las líneas que se escriban durante el pedido;
- se devuelve en la respuesta, en el mismo encabezado `X-Correlation-ID`
  (por ejemplo, se ve en Swagger al probar un endpoint);
- se usa en la línea que el middleware escribe al terminar cada pedido, con
  `metodo`, `ruta`, `estado` y `duracion_ms`.

El gateway (Traefik) deja pasar el encabezado sin cambios.

### Entre servicios (REST)

Los clientes REST internos reenvían el encabezado
([comunicación](05-comunicacion.md)), así que el identificador se mantiene en
Usuarios → Catálogo, Reservas → Catálogo, Reservas → Usuarios y
Catálogo → Reservas. Los dos clientes que hacen la llamada en un hilo aparte
(para cortar por tiempo) leen el encabezado antes de pasar al hilo, porque el
hilo no hereda la variable de contexto.

### Por mensajería

1. Reservas agrega el `correlation_id` del pedido al payload del evento que
   guarda en el outbox (`turno.confirmado` o `turno.cancelado`).
2. El publicador fija ese `correlation_id` en su contexto mientras publica el
   evento y lo pone además en la propiedad `correlation_id` del mensaje AMQP.
3. El consumidor de Notificaciones lo toma del cuerpo (o de la propiedad AMQP,
   si el cuerpo no se puede leer) y lo usa en sus logs mientras procesa el
   mensaje.
4. El envío de los mails ocurre después, en otro ciclo, y no tiene
   `correlation_id`: se asocia con la reserva por `id_turno`
   ([ADR 010](decisiones/010-correlation-id-en-eventos-y-envio.md)).

## Eventos de negocio

Además de la línea de cada pedido HTTP, se registran estos eventos:

| Servicio | Evento | Nivel | Campos propios |
| --- | --- | --- | --- |
| Usuarios | Paciente registrado / Profesional registrado | INFO | `tipo_usuario`, `id_especialidad` (profesional) |
| Usuarios | Alta de profesional no completada (catálogo caído o falla al confirmar) | WARNING | `compensa` |
| Usuarios | No se pudo compensar el alta en catálogo | ERROR | — |
| Catálogo | Disponibilidad creada | INFO | `id_disponibilidad`, `fecha_disponibilidad`, `horario_inicio`, `horario_fin` |
| Catálogo | Disponibilidad eliminada | INFO | `id_disponibilidad` |
| Catálogo | Borrado rechazado: la disponibilidad tiene un turno | WARNING | `id_disponibilidad`, `motivo` = `DISPONIBILIDAD_CON_TURNO` |
| Catálogo | Reservas no responde (listados sin marcar, bloqueo sin compensar) | WARNING / ERROR | — |
| Reservas | Turno reservado | INFO | `id_turno`, `id_disponibilidad`, `id_servicio` |
| Reservas | Turno cancelado | INFO | `id_turno`, `id_disponibilidad`, `cancelado_por` |
| Reservas | Reserva rechazada | WARNING | `id_disponibilidad`, `motivo` = `HORARIO_YA_RESERVADO`, `FRANJA_BLOQUEADA` o `CATALOGO_NO_DISPONIBLE` |
| Reservas | Usuarios no responde (agenda sin nombres) | WARNING | — |
| Publicador | Evento publicado | INFO | `id_evento`, `tipo_evento`, `id_turno` |
| Publicador | No se pudo publicar; reintento | WARNING | — |
| Notificaciones | Evento procesado | INFO | `id_evento`, `tipo_evento`, `id_turno`, `resultado` = `nuevo` o `duplicado` |
| Notificaciones | El turno ya tenía notificaciones de ese tipo; se ignora el evento | WARNING | — |
| Notificaciones | Mensaje inválido, va a la DLQ | ERROR | — |
| Notificaciones | No se pudo registrar el evento; se reencola | WARNING | — |
| Notificaciones | Consumidor desconectado; reintento | WARNING | — |
| Notificaciones | Mail enviado / no enviado, se reintenta / fallido | INFO / WARNING / ERROR | `id_notificacion`, `id_turno`, `tipo_notificacion`, `destinatario`, `intentos`, `ultimo_error` |

Las pruebas `tests/test_logs_de_negocio.py` (Usuarios, Catálogo y Reservas),
`tests/test_consumidor.py` y `tests/test_envio.py` (Notificaciones) verifican
estas líneas y su `correlation_id`.

### Datos personales

Los eventos nuevos se identifican con ids y roles, no con datos personales:
`destinatario` es `PACIENTE` o `PROFESIONAL`, no la dirección de correo, y en
los registros de usuario va el tipo, no el email. Ante una falla de la base
se registra solo el tipo de error, porque el texto de los errores de
SQLAlchemy incluye los parámetros del INSERT (email y hash de la
contraseña). Las pruebas comprueban que esas líneas no tengan emails ni
contraseñas.

Quedan con email dos advertencias anteriores de Usuarios: la del profesional
que ya existía en catálogo con otros datos y la de la compensación que no se
pudo hacer. Son casos para revisar a mano, y el email es lo que hace falta
para encontrar el registro.

## Cómo seguir una reserva

1. Tomar el `correlation_id` del encabezado `X-Correlation-ID` de la
   respuesta (o mandar uno propio en el pedido).
2. Filtrar por ese valor en todos los servicios:

   ```sh
   docker compose logs --no-log-prefix usuarios catalogo-medicos reservas reservas-publicador notificaciones \
     | grep '"correlation_id": "6f1c2a9e-1b7d-4c55-9a43-0d2f8e7b5a10"'
   ```

   Se ven el pedido en Reservas, la consulta a Catálogo, el turno reservado,
   la publicación del evento y su procesamiento en Notificaciones, que
   registra el `id_turno`.

3. Filtrar el envío de los mails por ese `id_turno`:

   ```sh
   docker compose logs --no-log-prefix notificaciones | grep '"id_turno": 15,'
   ```

Con [`jq`](https://jqlang.org) (herramienta externa, opcional) se puede
filtrar por campo y ordenar por fecha. Ordenar importa porque
`docker compose logs` agrupa las líneas por servicio, no en orden
cronológico. `fromjson?` descarta las líneas que no son JSON (la salida de
las migraciones al arrancar):

```sh
docker compose logs --no-log-prefix usuarios catalogo-medicos reservas reservas-publicador notificaciones \
  | jq -cR 'fromjson? | select(.correlation_id == "6f1c2a9e-1b7d-4c55-9a43-0d2f8e7b5a10")' \
  | jq -s -c 'sort_by(.fecha)[]'
```

Para ver solo problemas: `jq -cR 'fromjson? | select(.nivel == "WARNING" or .nivel == "ERROR")'`.

## Estado de los componentes

- Cada servicio expone `GET /salud`. En Notificaciones responde `503` si el
  consumidor perdió la conexión con RabbitMQ, e informa la fecha del último
  ciclo de envío.
- Docker Compose usa healthchecks para arrancar cada servicio cuando sus
  dependencias están listas.
- El panel de RabbitMQ (<http://localhost:15672>) muestra las colas, la DLQ y
  los mensajes pendientes; Mailpit (<http://localhost:8025>) muestra los
  correos enviados.
