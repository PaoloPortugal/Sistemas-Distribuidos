# 003 — Horarios libres y borrado de disponibilidades

**Estado:** propuesta. Se decide cuando se implemente el servicio de reservas.

## Contexto

Catálogo ya permite que cada profesional cargue sus franjas (DISPONIBILIDAD)
y que cualquier usuario autenticado las consulte. Lo que todavía no puede
hacer es:

1. **Marcar qué franjas están libres.** Una franja está ocupada si tiene un
   TURNO con estado RESERVADO (RNE: como máximo uno por disponibilidad). Los
   turnos viven en reservas, y catálogo no accede a sus tablas.
2. **Borrar una franja.** En el modelo relacional,
   `TURNO.id_disponibilidad → DISPONIBILIDAD` es `ON DELETE RESTRICT`: una
   franja con turnos no se borra (sus turnos se cancelan). Esa FK cruza
   servicios, así que PostgreSQL no la puede hacer cumplir.

Hoy `GET /profesionales/{email}/disponibilidades` devuelve todas las franjas,
sin indicar si están reservadas, y no hay endpoint para borrar.

## Opciones

### A. Catálogo consulta a reservas por REST

Al listar, catálogo le pide a reservas qué disponibilidades de ese rango
tienen un turno RESERVADO (por ejemplo
`POST /interno/disponibilidades-ocupadas` con los ids). Para borrar, le
pregunta si la franja tiene turnos.

- **Diagrama de arquitectura:** no cambia; ya existe Catálogo ↔ Reservas por
  REST.
- **Consistencia:** inmediata; la respuesta refleja el estado de reservas en
  ese momento.
- **Disponibilidad:** si reservas está caído, el listado no puede marcar las
  franjas libres (habría que fallar o devolverlas sin marcar) y no se puede
  borrar.
- **Acoplamiento:** una llamada síncrona por listado. Reservas tiene que
  exponer endpoints internos, también ocultos en Traefik.

### B. Catálogo mantiene una copia consumiendo eventos

Catálogo se suscribe al exchange `turnos` y consume `turno.confirmado` y
`turno.cancelado` para mantener, por cada disponibilidad, si está ocupada.

- **Diagrama de arquitectura:** agrega **RabbitMQ → Catálogo** (hoy solo
  consume Notificaciones).
- **Consistencia:** eventual. Entre que reservas confirma un turno y catálogo
  procesa el evento, el listado puede mostrar como libre una franja ya
  tomada. No rompe la regla de un turno por franja: **reservas sigue siendo
  la autoridad final** y rechaza la segunda reserva con su índice único
  parcial.
- **Disponibilidad:** el listado funciona aunque reservas esté caído.
- **Requisitos:** consumidor idempotente que registre los `event_id`
  procesados (CLAUDE.md); los eventos tienen que traer `id_disponibilidad`.
  Si se pierde un evento o el consumidor estuvo caído, hace falta una forma
  de reconstruir la copia.
- **Borrado:** catálogo puede rechazar el borrado de una franja que su copia
  marca como ocupada, pero por la consistencia eventual igual conviene que
  reservas confirme (o que el borrado sea una cancelación en reservas).

## Pendiente de decidir

- Cuál de las dos opciones usar para marcar franjas libres.
- Cómo se borra una franja: endpoint en catálogo que consulta a reservas, o
  flujo que pasa por reservas (cancelar los turnos y después borrar).
- Actualizar el diagrama de arquitectura según la opción elegida.
