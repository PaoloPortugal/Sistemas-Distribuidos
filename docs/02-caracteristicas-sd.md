# Características de los sistemas distribuidos

Para cada característica relevante se indica por qué importa en una clínica y
cómo la aborda lo que ya está implementado.

## Concurrencia

**Relevancia:** es el riesgo central del dominio. Si dos pacientes confirman
el mismo horario a la vez, una consulta previa del tipo "¿está libre?" no
alcanza: los dos la pasan y se genera una doble reserva.

**Cómo se aborda:** la decide PostgreSQL, no la aplicación. TURNO tiene un
índice único parcial `UNIQUE (id_disponibilidad) WHERE estado = 'RESERVADO'`:
la segunda inserción falla y reservas responde 409. La prueba
`pruebas/concurrencia/test_doble_reserva.py` lanza 10 reservas simultáneas del
mismo horario y comprueba un solo 201, nueve 409 y un solo turno RESERVADO.

El mismo criterio se aplica en otros puntos:

- dos horarios superpuestos de un profesional los rechaza un `EXCLUDE USING
  gist` sobre el rango horario;
- un email o un documento duplicado lo detectan las restricciones de la base,
  no una consulta previa;
- dos cancelaciones simultáneas del mismo turno se serializan con
  `SELECT … FOR UPDATE`.

## Consistencia

**Relevancia:** cada servicio es dueño de sus datos, así que las reglas que
cruzan servicios no las puede hacer cumplir una FK.

**Cómo se aborda:**

| Regla entre servicios | Cómo se garantiza |
| --- | --- |
| Todo usuario PROFESIONAL existe en PROFESIONAL (especialización total del MER) | Usuarios crea el USUARIO sin confirmar, pide a Catálogo el PROFESIONAL y confirma solo si responde bien; si no, deshace o compensa borrándolo ([ADR 002](decisiones/002-registro-profesional-compensacion.md)) |
| El servicio de un turno es de la especialidad del profesional | Reservas consulta a Catálogo al reservar ([ADR 006](decisiones/006-copia-franja-en-turno.md)) |
| Todo turno tiene su notificación | El evento se guarda en un outbox en la misma transacción que el turno y Notificaciones crea una notificación para el paciente y otra para el profesional al consumirlo ([ADR 005](decisiones/005-outbox-eventos-turno.md), [ADR 008](decisiones/008-notificaciones.md)): consistencia eventual |

Las copias de datos entre servicios (nombre del profesional en Catálogo,
datos del horario en TURNO) se toman del origen al crearse y se documentan
como desnormalización deliberada
([ADR 004](decisiones/004-copia-nombre-profesional.md),
[ADR 006](decisiones/006-copia-franja-en-turno.md)).

## Tolerancia a fallos y disponibilidad

**Relevancia:** un servicio caído no debería dejar el sistema en un estado
inválido ni frenar operaciones que no lo necesitan.

**Cómo se aborda:**

- **Fallos en una operación distribuida:** si Catálogo no responde al
  registrar un profesional, Usuarios responde 503 y no crea nada. Un timeout
  es ambiguo (Catálogo pudo haber creado el profesional), así que también se
  compensa; las operaciones internas son idempotentes y eso hace seguro
  reintentar.
- **Degradación parcial:** con Catálogo caído no se puede reservar (503, sin
  crear nada), pero la agenda y las cancelaciones siguen funcionando, porque
  TURNO guarda una copia de los datos del horario.
- **Eventos que no se pierden:** Reservas guarda cada evento en un outbox en
  la misma transacción que el turno. Un publicador aparte lo envía a RabbitMQ
  y lo marca como publicado solo cuando el broker confirma. Si RabbitMQ está
  caído, los eventos esperan en la tabla y reservar sigue funcionando.
- **Entrega "al menos una vez" e idempotencia:** si el publicador se cae
  entre publicar y marcar, el evento se publica de nuevo. Notificaciones
  registra cada `id_evento` procesado en la misma transacción que sus
  notificaciones, así que un evento repetido no genera avisos duplicados
  ([ADR 008](decisiones/008-notificaciones.md)).
- **Consumidor caído o correo caído:** los mensajes esperan en la cola durable
  hasta que Notificaciones vuelve. Si el servidor de correo no responde, la
  notificación queda PENDIENTE y se reintenta con espera creciente; después
  de 8 intentos pasa a FALLIDO. Un mensaje inválido va a una cola de mensajes
  rechazados (DLQ) en lugar de reintentarse para siempre.
- **Probado:** `pruebas/e2e/test_fallos_parciales.py` detiene Notificaciones,
  RabbitMQ, el publicador y Mailpit, y comprueba que, al volver, llegan todos
  los mails y ninguno se repite.

El único duplicado que no se puede descartar es el de un mail aceptado por el
servidor de correo justo antes de que se caiga el proceso de envío: un efecto
externo no puede ser parte de la transacción de la base
([ADR 008](decisiones/008-notificaciones.md)).
- **Arranque ordenado:** los servicios esperan a que PostgreSQL y RabbitMQ
  pasen su healthcheck antes de arrancar.

## Transparencia

**Relevancia:** el cliente no debería conocer cuántos servicios hay ni dónde
corren.

**Cómo se aborda:** el cliente habla solo con el API Gateway (Traefik), que
enruta por prefijo (`/api/usuarios`, `/api/catalogo-medicos`,
`/api/reservas`). Los endpoints de uso interno (`/interno/...`) solo son
accesibles dentro de la red de Docker: el gateway no los publica.

## Escalabilidad

**Relevancia:** la consulta de profesionales y horarios es la operación más
frecuente; la reserva es la más crítica.

**Cómo se aborda:** cada servicio es independiente y no guarda estado en
memoria (el estado está en PostgreSQL y la sesión en el JWT), así que se puede
escalar por separado. Cada servicio valida el token con la clave pública, sin
consultar a Usuarios en cada pedido. El listado de profesionales no depende de
Usuarios gracias a la copia del nombre
([ADR 004](decisiones/004-copia-nombre-profesional.md)). Antes de levantar
varias réplicas hay que resolver las migraciones al arrancar
([ADR 001](decisiones/001-migraciones-al-arrancar.md)).

## Seguridad

**Relevancia:** el sistema maneja datos personales y cada usuario solo puede
operar sobre lo suyo.

**Cómo se aborda:** contraseñas con hash argon2; JWT firmado con RS256, donde
solo Usuarios tiene la clave privada; autorización por rol y por dueño (un
paciente solo ve y cancela sus turnos, un profesional solo carga sus horarios,
y el email se toma del token, no del cuerpo del pedido). El login responde el
mismo mensaje y en un tiempo similar exista o no el email. Las claves y
contraseñas no están en el repositorio.

<!-- Pendiente de completar cuando se implemente: la observabilidad. -->
