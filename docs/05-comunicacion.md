# Comunicación: REST y eventos por RabbitMQ

## REST interno: usuarios → catalogo_medicos

Lo usa el registro de profesionales (ver
[ADR 002](decisiones/002-registro-profesional-compensacion.md)). USUARIO vive
en `usuarios` y PROFESIONAL en `catalogo_medicos`; como no hay FK ni
transacción entre servicios, `usuarios` le pide a catálogo que cree el
PROFESIONAL y, si su propio commit falla, le pide que lo borre (compensación).

- Base: `URL_CATALOGO` (en Docker Compose, `http://catalogo-medicos:8002`).
- Timeout del cliente: `TIMEOUT_CATALOGO_SEGUNDOS` (3 s por defecto).
- Las rutas `/interno/...` solo se usan dentro de la red de Docker: Traefik no
  las publica (la regla del router de catálogo excluye
  `/api/catalogo-medicos/interno`).
- Ambas operaciones son **idempotentes por email**, para que reintentar o
  compensar después de un timeout sea seguro.
- Los errores tienen la forma `{"detail": "<mensaje>", "codigo": "<CODIGO>"}`.
  El cliente decide por `codigo`, no por el texto.

### POST /interno/profesionales

Crea el PROFESIONAL de un USUARIO de tipo PROFESIONAL.

```json
{
  "email": "dr.gomez@ejemplo.com",
  "matricula": "MP-12345",
  "id_especialidad": 1,
  "nombre": "Bruno",
  "apellido": "Gómez"
}
```

`nombre` y `apellido` son una **copia** de USUARIO, solo para que catálogo
pueda mostrar el listado de profesionales sin consultar a `usuarios`
([ADR 004](decisiones/004-copia-nombre-profesional.md)). Son obligatorios.

| Respuesta | Cuándo |
| --- | --- |
| `201 Created` | Se creó el profesional. |
| `200 OK` | Ya existía un profesional con ese email y **la misma matrícula y especialidad** (idempotente). Si nombre o apellido cambiaron, se actualiza la copia. |
| `409` `MATRICULA_DUPLICADA` | La matrícula pertenece a otro profesional. |
| `409` `EMAIL_CON_OTROS_DATOS` | Ya existe un profesional con ese email y otra matrícula o especialidad. |
| `422` `ESPECIALIDAD_INEXISTENTE` | `id_especialidad` no existe en ESPECIALIDAD. |

El email llega ya normalizado a minúsculas por `usuarios`.

### DELETE /interno/profesionales/{email}

Borra el PROFESIONAL (se usa como compensación). El email va codificado en la
URL (`@` → `%40`).

| Respuesta | Cuándo |
| --- | --- |
| `204 No Content` | Se borró, **o no existía** (idempotente). |
| `409` `PROFESIONAL_CON_DISPONIBILIDADES` | El profesional tiene disponibilidades: la FK `DISPONIBILIDAD.email_profesional` es `ON DELETE RESTRICT` y no se borra nada. |

En la compensación el 409 no debería ocurrir: el profesional se creó segundos
antes y todavía no tiene USUARIO confirmado para iniciar sesión y cargar
disponibilidades. Si ocurriera, `usuarios` lo trata como cualquier respuesta
distinta de 204: registra "Inconsistencia" en el log y responde 503 al cliente.

### Cómo interpreta `usuarios` las respuestas

| Respuesta de catálogo | Respuesta al cliente de `/registro/profesional` | ¿Compensa? |
| --- | --- | --- |
| 200 / 201 | 201 (si el commit en `usuarios` funciona) | Solo si después falla el commit |
| 409 `MATRICULA_DUPLICADA` | 409 "La matrícula ya está registrada" | No |
| 409 `EMAIL_CON_OTROS_DATOS` | 409 "El email ya está registrado" (se registra un aviso: es un profesional huérfano) | No |
| 422 `ESPECIALIDAD_INEXISTENTE` | 422 "La especialidad no existe" | No |
| Conexión rechazada, timeout de conexión o respuesta 4xx fuera del contrato (por ejemplo 404) | 503 | No: el pedido no se aplicó |
| Timeout de lectura, conexión cortada o 5xx | 503 | Sí: el pedido pudo haberse aplicado |

## REST interno: reservas → catalogo_medicos

Lo usa `POST /turnos` de reservas para validar la reserva y copiar los datos
de la franja en el turno ([ADR 006](decisiones/006-copia-franja-en-turno.md)).
Es una **consulta**: catálogo no cambia nada, así que si falla no hay nada que
compensar.

- Base: `URL_CATALOGO` (en Docker Compose, `http://catalogo-medicos:8002`).
- Timeout del cliente: `TIMEOUT_CATALOGO_SEGUNDOS` (3 s por defecto).
- Traefik no publica `/interno` (misma regla que arriba).

### GET /interno/disponibilidades/{id_disponibilidad}?id_servicio=

Devuelve en una sola llamada la franja, la especialidad de su profesional y el
servicio pedido.

```json
{
  "id_disponibilidad": 7,
  "email_profesional": "dr.gomez@ejemplo.com",
  "fecha": "2026-11-05",
  "horario_inicio": "09:00:00",
  "horario_fin": "09:30:00",
  "id_especialidad": 1,
  "servicio": {"id_servicio": 1, "nombre": "Consulta general", "id_especialidad": 1}
}
```

| Respuesta | Cuándo |
| --- | --- |
| `200 OK` | La franja y el servicio existen. **Catálogo solo informa**: devuelve 200 aunque el servicio sea de otra especialidad o la franja ya haya pasado. |
| `404` `DISPONIBILIDAD_INEXISTENTE` | No existe la disponibilidad. |
| `404` `SERVICIO_INEXISTENTE` | No existe el servicio. |

### Cómo interpreta `reservas` las respuestas

Las reglas las aplica reservas, en su dominio:

| Situación | Respuesta al cliente de `POST /turnos` |
| --- | --- |
| 200 y `servicio.id_especialidad ≠ id_especialidad` (coherencia del servicio) | 422 |
| 200 y la franja empieza ahora o ya pasó (según `ZONA_HORARIA`) | 422 |
| 200 y la franja ya tiene un turno RESERVADO (lo decide el índice único parcial) | 409 |
| 404 `DISPONIBILIDAD_INEXISTENTE` o `SERVICIO_INEXISTENTE` | 404 |
| Conexión rechazada, timeout o cualquier respuesta fuera del contrato | 503, sin crear nada |

## Eventos: exchange `turnos`

Reservas escribe cada evento en su **outbox** (`reservas.evento_saliente`) en
la misma transacción que el cambio del turno
([ADR 005](decisiones/005-outbox-eventos-turno.md)). Publicarlos en RabbitMQ
y consumirlos en notificaciones es la próxima etapa.

| Evento | Cuándo |
| --- | --- |
| `turno.confirmado` | Se reservó un turno. |
| `turno.cancelado` | Se canceló un turno (paciente o profesional). |

No existe `turno.modificado`: modificar un turno es cancelarlo y reservar otro.

```json
{
  "id_evento": "6f1c2b9e-…",
  "tipo": "turno.cancelado",
  "ocurrido_en": "2026-11-02T10:00:00-03:00",
  "id_turno": 15,
  "id_disponibilidad": 7,
  "id_servicio": 1,
  "email_paciente": "ana.perez@ejemplo.com",
  "email_profesional": "dr.gomez@ejemplo.com",
  "fecha": "2026-11-05",
  "horario_inicio": "09:00:00",
  "horario_fin": "09:30:00",
  "cancelado_por": "PACIENTE",
  "motivo": "Viaje"
}
```

`cancelado_por` y `motivo` solo vienen en `turno.cancelado`. `id_evento` es el
`event_id` con el que el consumidor descarta duplicados (la entrega es "al
menos una vez").
