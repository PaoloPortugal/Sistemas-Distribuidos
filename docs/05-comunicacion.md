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
{"email": "dr.gomez@ejemplo.com", "matricula": "MP-12345", "id_especialidad": 1}
```

| Respuesta | Cuándo |
| --- | --- |
| `201 Created` | Se creó el profesional. |
| `200 OK` | Ya existía un profesional con ese email y **los mismos datos** (idempotente). |
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

### Cómo interpreta `usuarios` las respuestas

| Respuesta de catálogo | Respuesta al cliente de `/registro/profesional` | ¿Compensa? |
| --- | --- | --- |
| 200 / 201 | 201 (si el commit en `usuarios` funciona) | Solo si después falla el commit |
| 409 `MATRICULA_DUPLICADA` | 409 "La matrícula ya está registrada" | No |
| 409 `EMAIL_CON_OTROS_DATOS` | 409 "El email ya está registrado" (se registra un aviso: es un profesional huérfano) | No |
| 422 `ESPECIALIDAD_INEXISTENTE` | 422 "La especialidad no existe" | No |
| Conexión rechazada, timeout de conexión o respuesta 4xx fuera del contrato (por ejemplo 404) | 503 | No: el pedido no se aplicó |
| Timeout de lectura, conexión cortada o 5xx | 503 | Sí: el pedido pudo haberse aplicado |
