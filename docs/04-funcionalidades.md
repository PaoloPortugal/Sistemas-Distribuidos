# Funcionalidades implementadas

Las cuatro funcionalidades están operativas y se pueden probar desde el
Swagger de cada servicio (`http://localhost:8080/api/<servicio>/docs`), a
través del gateway. Las rutas de abajo son relativas al prefijo de cada
servicio.

## 1. Registro y autenticación de usuarios

Servicio: **Usuarios** (`/api/usuarios`).

| Endpoint | Quién | Qué hace |
| --- | --- | --- |
| `POST /registro/paciente` | Cualquiera | Crea USUARIO y PACIENTE en una transacción. 409 si el email o el documento ya existen. |
| `POST /registro/profesional` | Cualquiera | Crea USUARIO y, en Catálogo, PROFESIONAL con matrícula y especialidad, con compensación si algo falla. 409 por email o matrícula repetidos, 422 si la especialidad no existe, 503 si Catálogo no responde. |
| `POST /login` | Cualquiera | Devuelve un JWT RS256 con el email y el tipo de usuario, válido 60 minutos. 401 con el mismo mensaje si el email no existe o la contraseña es incorrecta. |
| `GET /yo` | Autenticado | Devuelve el perfil del usuario del token. |

El tipo de usuario del token habilita las operaciones de cada rol en los demás
servicios.

## 2. Gestión de profesionales y disponibilidad

Servicio: **Catálogo** (`/api/catalogo-medicos`).

| Endpoint | Quién | Qué hace |
| --- | --- | --- |
| `GET /especialidades` | Autenticado | Lista las especialidades. |
| `GET /especialidades/{id}/servicios` | Autenticado | Lista los servicios de una especialidad. |
| `GET /profesionales?id_especialidad=` | Autenticado | Lista profesionales con nombre, matrícula y especialidad; el filtro es opcional. |
| `GET /profesionales/{email}/disponibilidades?desde=&hasta=` | Autenticado | Horarios de un profesional (por defecto, los próximos 30 días). |
| `POST /disponibilidades` | Profesional | Crea un horario propio. 409 si se superpone con otro, 422 si el inicio no es anterior al fin o si está en el pasado. |
| `GET /mis-disponibilidades` | Profesional | Horarios propios. |

La especialidad del profesional se registra en el alta (funcionalidad 1).

<!-- Pendiente: modificar y eliminar horarios (ADR 003), y marcar qué
horarios están libres en el listado. -->

## 3. Consulta y reserva de turnos

Servicio: **Reservas** (`/api/reservas`), junto con la consulta de Catálogo.

| Endpoint | Quién | Qué hace |
| --- | --- | --- |
| `POST /turnos` | Paciente | Reserva un horario para un servicio. Valida contra Catálogo que el horario exista y no haya pasado, y que el servicio sea de la especialidad del profesional (422). Si el horario ya está reservado, 409. |

La verificación de que el turno sigue disponible al confirmar la hace
PostgreSQL con un índice único parcial: aunque dos pacientes confirmen a la
vez, solo uno lo consigue.

## 4. Gestión y cancelación de reservas

Servicio: **Reservas** (`/api/reservas`).

| Endpoint | Quién | Qué hace |
| --- | --- | --- |
| `GET /mis-turnos` | Paciente | Sus turnos. |
| `GET /agenda?desde=&hasta=` | Profesional | Los turnos de sus horarios. |
| `POST /turnos/{id}/cancelar` | Paciente o profesional dueño | Cancela el turno con un motivo opcional. El paciente puede cancelar hasta 24 h antes del inicio; el profesional, hasta el inicio (422 fuera de plazo). 403 si el turno es de otro, 409 si ya no está reservado. |

Al cancelar, el horario vuelve a quedar disponible y otro paciente lo puede
reservar.

## Notificaciones

Cada reserva y cada cancelación generan un evento outbox y, cuando el
publicador confirma su entrega en RabbitMQ, un mail al paciente y otro al
profesional, con la fecha, el horario y, en las cancelaciones, quién canceló
y el motivo. El consumidor registra cada `id_evento` procesado para evitar
duplicados y reintenta fallos transitorios. En desarrollo los mails se ven en
Mailpit (`http://localhost:8025`). Los mails no llevan nombres, solo los emails
([ADR 008](decisiones/008-notificaciones.md)).

## Pruebas

| Servicio | Tests automáticos (pytest) |
| --- | --- |
| Usuarios | 55 |
| Catálogo | 81 |
| Reservas | 82 |
| Notificaciones | 24 |

Además, contra el sistema levantado con Docker:

- `pruebas/concurrencia/test_doble_reserva.py`: 10 pacientes reservan el mismo
  horario a la vez y queda exactamente un turno RESERVADO.
- `pruebas/e2e/test_fallos_parciales.py`: con Notificaciones, RabbitMQ, el
  publicador o Mailpit detenidos, al volver llegan todos los mails sin
  duplicados.

<!-- Pendiente: capturas de cada funcionalidad. -->
