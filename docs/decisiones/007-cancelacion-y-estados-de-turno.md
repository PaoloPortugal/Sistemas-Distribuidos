# 007 — Plazo de cancelación según quién cancela, y estado FINALIZADO

**Estado:** aceptada. Ya reflejada en la RNE del MER y en el PDF del modelo
relacional.

## Plazo de cancelación

### Contexto

La RNE original del MER decía: "Un turno solo puede cancelarse si
fecha_cancelacion + 24 h < fecha de su disponibilidad". No distinguía quién
cancela.

### Decisión

El plazo depende de `cancelado_por`:

| Quién cancela | Regla | Si no se cumple |
| --- | --- | --- |
| **Paciente** (`cancelado_por = PACIENTE`) | Solo si `fecha_cancelacion + 24 h < fecha + horario_inicio` | 422 |
| **Profesional** (`cancelado_por = PROFESIONAL`) | En cualquier momento **antes** de `fecha + horario_inicio` | 422 (el turno ya empezó) |

Las dos comparaciones son estrictas: con exactamente 24 h de anticipación el
paciente ya no puede cancelar, y el profesional no puede cancelar en el minuto
en que empieza el turno.

**Motivo:** es más realista para una clínica. El profesional puede tener una
urgencia el mismo día y tiene que poder avisar al paciente (la cancelación
genera `turno.cancelado` y su notificación). El paciente, en cambio, tiene un
plazo para que el horario se pueda volver a ofrecer.

### Fuentes de verdad

- La RNE original aplicaba el plazo de 24 h a cualquier cancelación; con esta
  decisión se aplica solo al paciente.
- **Ya reflejado:** la RNE del MER ("Cancelación: si cancela el PACIENTE…; si
  cancela el PROFESIONAL…") y las restricciones generales del PDF del modelo
  relacional ("Plazo de cancelación según quién cancela") dicen lo mismo que
  esta decisión.

### Detalles

- "Ahora" y el inicio del turno se comparan como instantes en la zona
  `ZONA_HORARIA` (America/Montevideo): la fecha y el horario de la franja son
  locales de la clínica, y el contenedor corre en UTC.
- Quién cancela se decide con el token: el paciente dueño del turno
  (`tipo = PACIENTE` y `sub = email_paciente`) o el profesional dueño de la
  franja (`tipo = PROFESIONAL` y `sub = email_profesional`, copiado en TURNO,
  ADR 006). Cualquier otro → 403.
- Solo se cancela un turno RESERVADO; uno CANCELADO o FINALIZADO → 409.
- El motivo es opcional (el relacional solo exige `fecha_cancelacion` y
  `cancelado_por`).
- Al cancelar, la franja queda libre sin tocar catálogo: el índice único
  parcial solo mira los turnos RESERVADO.

## Estado FINALIZADO

### Decisión

**Fuera de alcance por ahora.** El CHECK de `estado` lo admite, pero nada lo
asigna: los turnos pasados quedan como RESERVADO.

Mientras tanto no rompe ninguna regla: un turno pasado no se puede cancelar
(por el plazo) y su franja no se puede volver a reservar (está en el pasado).

### Evolución propuesta

Una **tarea periódica en reservas** que pase a FINALIZADO los turnos
RESERVADO cuyo `fecha + horario_fin` ya pasó.

- Es una consulta local gracias a la copia de la franja en TURNO (ADR 006).
- Con más de una réplica, la tarea tiene que correr en una sola a la vez (por
  ejemplo con `pg_advisory_lock`), por la misma razón que el ADR 001.
- Si hace falta distinguir "atendido" de "no se presentó", habría que agregar
  un estado al MER; hoy no está.
