# 010 — correlation_id en los eventos y en el envío de mails

**Estado:** aceptada e implementada. El MER, el modelo relacional y la
arquitectura no cambian; cambia el contrato del evento (campo nuevo y
opcional).

## Contexto

Cada pedido HTTP tiene un `correlation_id` (encabezado `X-Correlation-ID`)
que aparece en todos sus logs y se reenvía en los pedidos REST internos
([observabilidad](../08-observabilidad.md)). Una reserva, además, sigue por
mensajería: Reservas escribe el evento en el outbox, el publicador lo manda a
RabbitMQ, el consumidor de Notificaciones crea las NOTIFICACION y, más tarde,
otro ciclo del mismo servicio manda los mails. Para seguir una reserva de
punta a punta, el `correlation_id` tiene que cruzar también ese camino.

El último tramo es distinto de los demás: el envío no procesa un evento, sino
que toma NOTIFICACION en estado PENDIENTE de la base, en otra transacción y en
otro momento. Ahí no hay ningún `correlation_id` en el contexto.

## Opciones consideradas para el envío

| | A. Asociar por `id_turno` | B. Guardar el `correlation_id` en la base de notificaciones |
| --- | --- | --- |
| Modelo relacional | Sin cambios | Columna nueva en NOTIFICACION (o en la tabla técnica `envio_mail`) |
| Seguir un mail hasta la reserva | Dos filtros: `correlation_id` → `id_turno` (log del consumidor) → `id_turno` (log del envío) | Un solo filtro por `correlation_id` |
| Migración | No | Sí, en notificaciones |

## Decisión

**Opción A.**

1. **En el evento.** Reservas agrega `correlation_id` al payload del evento
   que escribe en el outbox, con el valor del pedido que reservó o canceló. Es
   opcional en el contrato: el consumidor acepta eventos sin él (los que
   quedaron en el outbox antes de este cambio) y no lo usa para ninguna regla
   de negocio.
2. **En el publicador.** Mientras publica un evento, el publicador fija el
   `correlation_id` del evento en su contexto, así sus logs lo incluyen. El
   mensaje AMQP lo lleva además en la propiedad `correlation_id`.
3. **En el consumidor.** Mientras procesa un mensaje, toma el
   `correlation_id` del cuerpo (o, si el cuerpo no se puede leer, el de la
   propiedad AMQP) y registra una línea por evento con ese `correlation_id`,
   el `id_turno`, el `id_evento` y el resultado (`nuevo` o `duplicado`).
4. **En el envío.** Cada resultado (enviado, reintento o fallido) se registra
   con `id_turno`, `id_notificacion`, el tipo y el destinatario
   (`PACIENTE`/`PROFESIONAL`, no la dirección de correo), sin
   `correlation_id`. La asociación con la reserva se hace por `id_turno`.

Se descartó la opción B porque obliga a cambiar el modelo relacional, que es
fuente de verdad del proyecto, solo para ahorrar un filtro en los logs.

## Consecuencias

- Para seguir una reserva hasta sus mails: filtrar por `correlation_id` (da
  el recorrido por catálogo, reservas, el publicador y el consumidor, que
  registra el `id_turno`) y después filtrar el envío por ese `id_turno`.
- Un turno tiene como máximo una confirmación y una cancelación, y cada una
  viene de un pedido distinto: por `id_turno` más el tipo de notificación
  (`CONFIRMADO` / `CANCELADO`) se sabe a qué pedido corresponde cada mail.
- Si más adelante hace falta un único filtro, se puede pasar a la opción B
  sin cambiar el contrato del evento.
