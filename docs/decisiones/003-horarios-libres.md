# 003 — Horarios libres y borrado de disponibilidades

**Estado:** aceptada e implementada. **Cambia la arquitectura** (flecha
Catálogo → Reservas) y el texto del modelo relacional (el RESTRICT de
`TURNO.id_disponibilidad` aplica solo a turnos RESERVADO); el MER no cambia.

## Contexto

Catálogo guarda los horarios (DISPONIBILIDAD) y reservas los turnos. Faltaba:

1. **Marcar qué horarios están libres** (funcionalidad 3 de la letra). Un
   horario está ocupado si tiene un TURNO RESERVADO (RNE: como máximo uno por
   disponibilidad), y catálogo no accede a las tablas de reservas.
2. **Eliminar horarios** (funcionalidad 2). En el modelo relacional,
   `TURNO.id_disponibilidad → DISPONIBILIDAD` es `ON DELETE RESTRICT`, pero
   esa FK cruza servicios y PostgreSQL no la puede hacer cumplir.

## Opciones para marcar los horarios libres

| | A. Catálogo consulta a reservas por REST | B. Catálogo mantiene una copia con eventos |
| --- | --- | --- |
| Arquitectura | Flecha Catálogo → Reservas | Flecha RabbitMQ → Catálogo |
| Consistencia | Inmediata | Eventual: puede mostrar libre un horario ya tomado |
| Si reservas está caído | El listado no puede marcar | El listado funciona |
| Borrar | Reservas decide en el momento | La copia no alcanza: igual hay que preguntarle a reservas |

## Decisión

**Opción A**, con un bloqueo en reservas para borrar.

### Modificar es borrar y crear

No hay `PATCH`. Modificar un horario es borrarlo (`DELETE`) y crear otro con
el `POST /disponibilidades` que ya existía, igual que modificar un turno es
cancelarlo y reservar otro (ADR 007). Así la copia de la franja en TURNO
(ADR 006) nunca queda desactualizada: un horario con turno no se toca.

### Listados con `libre`

`GET /profesionales/{email}/disponibilidades` y `GET /mis-disponibilidades`
devuelven cada horario con `libre`:

- `true`: no empezó y no tiene turno RESERVADO ni bloqueo;
- `false`: ya empezó, o está ocupado o bloqueado;
- `null`: reservas no respondió (el listado sigue funcionando; si el
  horario estaba tomado, reservas igual rechaza la reserva con 409).

Con `?solo_libres=true` se devuelven solo los libres; si reservas no
responde, **503**, porque el filtro no se puede aplicar y devolver todos
daría a entender que están libres.

Catálogo consulta solo los horarios que no empezaron, con
`POST /interno/disponibilidades-ocupadas` (hasta 5000 ids). Timeout
`TIMEOUT_RESERVAS_SEGUNDOS` (2 s), que cubre también la resolución DNS: con
el contenedor de reservas detenido, resolver su nombre tarda unos 8 s y el
timeout de httpx no lo incluye, así que cada pedido corre en un hilo y se
espera como máximo ese tiempo.

### Borrar: bloqueo en reservas

Solo el profesional dueño, y solo si el horario no empezó (si no, 422).

El problema es una carrera: reservas consulta a catálogo
(`GET /interno/disponibilidades/{id}`) y recién después inserta el turno. Si
catálogo borra el horario entre esos dos pasos, quedaría un turno sobre un
horario que no existe, aunque catálogo le haya preguntado a reservas si
estaba libre. Un campo `activo` en DISPONIBILIDAD no lo evita (la reserva ya
pasó la consulta) y además cambiaba el MER.

La decisión la toma **reservas, que es la autoridad final**:

1. Catálogo toma la fila con `SELECT … FOR UPDATE` (dos borrados de la misma
   franja no se cruzan) y valida dueño y que no empezó.
2. Le pide a reservas `PUT /interno/bloqueos/{id}`. En una transacción,
   reservas responde 409 si el horario tiene un turno RESERVADO; si no,
   registra el bloqueo en `reservas.disponibilidad_bloqueada` (tabla
   técnica, fuera del MER) y responde 204. Es idempotente.
3. Catálogo borra el horario y responde 204.

Reservar mira el bloqueo **en la misma transacción que inserta el turno** y,
si está, responde 409 "El horario no está disponible en este momento".

Para que bloquear y reservar no se crucen dentro de reservas, los dos toman
un advisory lock de PostgreSQL por `id_disponibilidad`
(`pg_advisory_xact_lock(3, id)`): **exclusivo al bloquear y compartido al
reservar**. Bloquear ve el turno de una reserva que llegó antes; reservar ve
el bloqueo de un borrado que llegó antes. Dos reservas del mismo horario
siguen corriendo a la vez y las decide el índice único parcial. Nadie
mantiene una transacción abierta durante una llamada HTTP, así que no hay
deadlocks entre servicios.

**El bloqueo de un horario borrado queda para siempre.** Si se quitara, una
reserva que consultó a catálogo antes del borrado podría pasar después. Los
ids no se reutilizan (Identity), así que cuesta una fila por horario borrado.

**Compensación:** si catálogo no pudo borrar después de pedir el bloqueo
(reservas no respondió a tiempo, o falló el commit), pide
`DELETE /interno/bloqueos/{id}` y responde 503. Si eso también falla, el
horario sigue en catálogo pero figura ocupado; repetir el borrado lo
destraba, porque bloquear es idempotente.

### Turnos cancelados de un horario que se borra

Se borra igual. Los turnos CANCELADO conservan su copia de fecha, horario y
profesional (ADR 006), así que el historial no se pierde; su
`id_disponibilidad` queda como referencia a un horario que ya no existe. El
RESTRICT del modelo relacional aplica solo a turnos RESERVADO.

## Respuestas de `DELETE /disponibilidades/{id}`

| Código | Cuándo |
| --- | --- |
| 204 | Se borró |
| 403 | No es un profesional, o el horario es de otro profesional |
| 404 | El horario no existe (o ya se borró) |
| 409 | Tiene un turno RESERVADO: hay que cancelarlo antes |
| 422 | Ya empezó |
| 503 | Reservas no respondió; no se borró nada |

## Consecuencias

- **Arquitectura:** flecha nueva Catálogo → Reservas (REST interno). Traefik
  no publica `/api/reservas/interno`, igual que el `/interno` de catálogo.
- **Disponibilidad:** con reservas caído el listado sale sin marcar, el
  filtro `solo_libres` responde 503 y no se puede borrar. Catálogo arranca
  igual (no tiene `depends_on` hacia reservas).
- **Pruebas:** `pruebas/concurrencia/test_reservar_vs_borrar.py` corre 20
  rondas en las que el profesional borra un horario mientras 5 pacientes lo
  reservan: en cada una gana el borrado (ningún turno) o una reserva (el
  borrado responde 409 y hay exactamente un turno).
- **Modelo relacional (lo actualiza el equipo):** la fila de
  `TURNO.id_disponibilidad` y una restricción general nueva: no se borra un
  horario con turno RESERVADO ni uno que ya empezó.
