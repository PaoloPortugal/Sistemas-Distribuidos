# 005 — Outbox para los eventos de turno

**Estado:** aceptada e implementada: reservas escribe el outbox y el proceso
`reservas-publicador` lo publica en RabbitMQ. El consumo está en el ADR 008.

## Contexto

El MER define la participación de TURNO en "notifica" como **total**: todo
turno tiene al menos una notificación (la de confirmación). NOTIFICACION vive
en el servicio de notificaciones, que se entera de los turnos por los eventos
`turno.confirmado` y `turno.cancelado` del exchange `turnos`.

Si el evento se pierde, el turno queda sin notificación y se rompe esa regla.
El problema es la **escritura doble**: el turno va a PostgreSQL y el evento a
RabbitMQ, y no hay una transacción que abarque los dos.

## Opciones consideradas

| | A. Outbox transaccional | B. Publicar después del commit | C. Publicar antes del commit |
| --- | --- | --- | --- |
| Si RabbitMQ está caído | El evento espera en la tabla | **Se pierde** | Falla la reserva, o se publica un evento sin turno |
| Si el proceso muere entre los dos pasos | No hay "entre": es una sola transacción | **Se pierde** | Evento de un turno que hizo rollback |
| Entrega | Al menos una vez | Como mucho una vez | Incorrecta |

## Decisión

**Opción A.** Tabla `reservas.evento_saliente`:

| Columna | |
| --- | --- |
| `id_evento` (UUID, PK) | Es el `event_id`: el consumidor lo registra para descartar duplicados (CLAUDE.md). |
| `tipo` | `turno.confirmado` o `turno.cancelado` (CHECK). |
| `payload` (JSONB) | El evento completo (contrato en `docs/05-comunicacion.md`). |
| `creado_en` | Cuándo ocurrió. |
| `publicado_en` | Nulo hasta que el publicador lo confirma. Un índice parcial sobre los pendientes acelera la búsqueda. |

- Reservar inserta el TURNO y su `turno.confirmado` **en la misma
  transacción**; cancelar actualiza el TURNO e inserta `turno.cancelado` en la
  misma transacción. Si el turno no se guarda, el evento tampoco, y al revés.
- El evento lleva fecha, horario y profesional (copiados en TURNO, ADR 006),
  así notificaciones puede armar el mensaje sin consultar a catálogo.
- Es una tabla técnica, como `alembic_version`: no forma parte del MER.

## Publicador

Proceso aparte: servicio `reservas-publicador` en Docker Compose, con la misma
imagen que reservas y el comando `python -m app.publicador` (un tipo de
proceso, en términos de 12-Factor). Código en `app/publicador.py`,
`app/eventos.py` y `app/dominio/publicacion.py`.

- Toma los eventos con `publicado_en` nulo en orden de `creado_en`, **uno por
  transacción**, con `SELECT … FOR UPDATE SKIP LOCKED`: varias réplicas no
  toman el mismo evento.
- Los publica en el exchange `turnos` (topic, durable) con routing key = tipo,
  `message_id` = `id_evento` y mensajes persistentes, en un canal con
  **publisher confirms**. Completa `publicado_en` **solo cuando el broker
  confirma**; si lo rechaza, el evento queda pendiente y no se saltea.
- Publica con `mandatory`: si todavía no hay ninguna cola ligada (por ejemplo,
  notificaciones nunca arrancó), el broker lo devuelve y el evento queda en
  el outbox, en lugar de descartarse en silencio.
- Si RabbitMQ o la base no responden, reintenta con espera creciente (1, 2,
  4… hasta 30 s). No corre migraciones (ADR 001): si las tablas no existen,
  también reintenta.
- Si se cae después de la confirmación y antes del commit, el evento se
  publica de nuevo: la entrega es "al menos una vez" y el consumidor descarta
  duplicados por `id_evento` (ADR 008).
- `PUBLICADOR_PAUSA_ENTRE_EVENTOS_SEGUNDOS` (0 por defecto) limita el ritmo; la
  prueba de fallos parciales c) la usa para matar al publicador a mitad de un
  lote.

### Por qué un proceso aparte y no una tarea dentro de la API

| | Proceso aparte (elegido) | Tarea dentro de la API |
| --- | --- | --- |
| Escala | Independiente de la API | Cada réplica de la API sería también un publicador |
| Fallos | Se puede reiniciar sin cortar la API; un problema con RabbitMQ no afecta a quien atiende pedidos | Comparte proceso con los pedidos |
| Arquitectura | Un contenedor más en el diagrama | Sin cambios |

## Consecuencias

- La participación total de TURNO en "notifica" queda garantizada **de forma
  eventual**: la NOTIFICACION se crea cuando notificaciones consume el evento,
  no en el mismo instante que el turno.
- **Ya reflejado en los diagramas:** la arquitectura muestra el outbox dentro
  de Reservas y la flecha a RabbitMQ como "publica evento (desde el outbox)";
  el PDF del modelo relacional explica que la participación total de TURNO en
  "notifica" se asegura con el outbox.
- Si RabbitMQ o el publicador están caídos, los eventos se acumulan en la
  tabla sin perderse y salen cuando vuelven (prueba de fallos parciales b).
