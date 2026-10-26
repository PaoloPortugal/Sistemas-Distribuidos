# 005 — Outbox para los eventos de turno

**Estado:** aceptada. En esta etapa reservas solo **escribe** el outbox;
publicarlo en RabbitMQ y el servicio de notificaciones van en la próxima.

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

## Próxima etapa: publicador

Un proceso en reservas lee los eventos con `publicado_en` nulo en orden de
`creado_en`, los publica en el exchange `turnos` con confirmación del broker
(publisher confirms) y recién entonces completa `publicado_en`.

- Si se cae después de publicar y antes de marcar, el evento se publica de
  nuevo: por eso la entrega es "al menos una vez" y el consumidor tiene que
  ser idempotente por `id_evento`.
- Con más de una réplica, cada una debería tomar eventos distintos
  (`SELECT … FOR UPDATE SKIP LOCKED`), por la misma razón que el ADR 001.

## Consecuencias

- La participación total de TURNO en "notifica" queda garantizada **de forma
  eventual**: la NOTIFICACION se crea cuando notificaciones consume el evento,
  no en el mismo instante que el turno.
- **Ya reflejado en los diagramas:** la arquitectura muestra el outbox dentro
  de Reservas y la flecha a RabbitMQ como "publica evento (desde el outbox)";
  el PDF del modelo relacional explica que la participación total de TURNO en
  "notifica" se asegura con el outbox.
- Hasta que exista el publicador, los eventos se acumulan en la tabla sin
  perderse.
