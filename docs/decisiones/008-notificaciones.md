# 008 — Notificaciones: idempotencia, destinatarios, envío y dead-letter

**Estado:** aceptada. **Cambia el MER y el modelo relacional** (atributo
`destinatario` en NOTIFICACION, con su CHECK y un UNIQUE); el equipo actualiza
los diagramas.

## Contexto

Todo turno confirmado o cancelado tiene que terminar en una NOTIFICACION y un
mail (participación total de TURNO en "notifica"), sin perder eventos ni
duplicar efectos aunque se caigan RabbitMQ, el publicador, notificaciones o el
servidor de correo. Los eventos llegan con entrega "al menos una vez"
(ADR 005): el mismo evento puede llegar dos veces.

## Decisiones

### 1. Idempotencia: tabla técnica `evento_procesado`

- `notificaciones.evento_procesado (id_evento PK, recibido_en)`. Es técnica,
  fuera del MER, como el outbox de reservas.
- Se inserta **en la misma transacción** que las NOTIFICACION y sus
  `envio_mail`. Si el `id_evento` ya está, la PK lo rechaza, no se crea nada y
  el mensaje se confirma igual (para que RabbitMQ no lo vuelva a entregar).
- El ack a RabbitMQ va **después del commit**: si el proceso se cae entre los
  dos, el mensaje se reentrega y la PK lo descarta.
- Segunda defensa: `UNIQUE (id_turno, tipo, destinatario)` en NOTIFICACION.
  Un turno se confirma una vez y se cancela como mucho una vez (volver a
  reservar crea otro turno).

Se descartó una columna `id_evento UNIQUE` en NOTIFICACION: cambiaba el MER y
no admite que un evento genere dos notificaciones.

### 2. Dos destinatarios: paciente y profesional

- Cada evento genera **dos NOTIFICACION**, una por destinatario, y dos
  `envio_mail`, en la misma transacción. Los dos reciben la confirmación y la
  cancelación.
- **Cambio en el MER y en el modelo relacional:** NOTIFICACION suma
  `destinatario ∈ {PACIENTE, PROFESIONAL}` con su CHECK, y el UNIQUE pasa a ser
  `(id_turno, tipo, destinatario)`:

  NOTIFICACION (**id_notificacion**, *id_turno*, tipo, estado_notificacion, destinatario)

- Textos distintos para cada uno (`app/dominio/mensajes.py`):
  - confirmado, al paciente: "Tu turno quedó confirmado para el <fecha> de
    <inicio> a <fin> con <email_profesional>";
  - confirmado, al profesional: "Tenés un nuevo turno el <fecha> de <inicio> a
    <fin> con <email_paciente>";
  - cancelado: los dos dicen quién canceló (`cancelado_por`) y el motivo si lo
    hay.
- Los dos mails se envían y se reintentan **por separado**: si uno falla, el
  otro sale igual.

### 3. Envío en dos pasos con los estados del MER

- `notificaciones.envio_mail`, 1:1 con NOTIFICACION y fuera del MER:
  `email_destinatario`, `asunto`, `cuerpo`, `intentos`, `proximo_intento`,
  `ultimo_error`, `enviado_en`. El mail se arma **una vez**, al consumir el
  evento.
- El consumidor crea la NOTIFICACION en **PENDIENTE**. El envío toma las
  PENDIENTE cuyo `proximo_intento` ya llegó (una por transacción, con
  `FOR UPDATE SKIP LOCKED`), manda el mail por SMTP y la pasa a **ENVIADO**.
- Si falla, suma un intento y reprograma con espera creciente: 5, 10, 20, 40,
  60, 60… segundos. Tras **8 intentos** pasa a **FALLIDO** y no se reintenta
  más (unos 4 minutos y medio en total).
- Todo es configurable por entorno: `MAX_INTENTOS_ENVIO` (8),
  `ESPERA_MINIMA_SEGUNDOS` (5), `ESPERA_MAXIMA_SEGUNDOS` (60).
- El encabezado `Message-ID` del mail es fijo por notificación
  (`notificacion-<id>`).

### 4. Mensajes inválidos y dead-letter queue

- La cola `notificaciones.turnos` es **quorum**, con
  `x-dead-letter-exchange: turnos.dlx` y `x-delivery-limit: 5`
  (`LIMITE_ENTREGAS`). `prefetch` de 10 (`PREFETCH`).
- Un mensaje que no cumple el contrato se rechaza sin reencolar y va a
  `notificaciones.turnos.dlq`: no se reintenta para siempre.
- Si falla por algo transitorio (la base no responde), el consumidor espera a
  que la base vuelva y recién entonces lo reencola. Cada reencolado cuenta;
  tras 5 entregas va a la DLQ. Así un mensaje que siempre falla no bloquea la
  cola.
- Los mensajes de la DLQ se revisan a mano desde el panel de RabbitMQ. Falta
  una herramienta para reprocesarlos.

### 5. Procesos

Notificaciones corre en **un solo contenedor**, con el consumidor y el envío
como dos tareas `asyncio` dentro de uvicorn. `/salud` responde 503 si el
consumidor perdió la conexión con RabbitMQ, y el healthcheck de Docker Compose
usa ese endpoint.

### 6. Datos del mail: sin nombres (opción C)

Los mails usan solo los datos del evento: el email del profesional y del
paciente, la fecha, el horario y, en las cancelaciones, quién canceló y el
motivo. No se consulta a otros servicios ni se cambió el contrato del evento.

**Mejora futura (opción A):** copiar en TURNO, al reservar, el nombre del
servicio y el nombre y apellido del profesional (como el ADR 006) y mandarlos
en los dos eventos. Cambiaría el MER y el modelo relacional (TURNO suma
`nombre_servicio` y `nombre_profesional` como copia), el contrato del evento y
el endpoint interno `GET /interno/disponibilidades/{id}` de catálogo, que hoy
no devuelve el nombre del profesional.

## Ventana de duplicado en el envío SMTP

El servidor de correo **no participa de la transacción** de la base. Si el
proceso se cae después de que el servidor aceptó el mail y antes del commit
que lo marca ENVIADO, al volver la NOTIFICACION sigue PENDIENTE y el mail se
manda otra vez.

No se puede eliminar: no existe el "exactamente una vez" con un efecto
externo. Hay que elegir entre "como mucho una vez" (marcar antes de enviar:
se puede perder el mail) y "al menos una vez" (marcar después: se puede
repetir). Para un aviso de turno es preferible un mail repetido a uno perdido.
La ventana es lo que tarda el commit, del orden de milisegundos. El
`Message-ID` fijo por notificación permite que un cliente de correo reconozca
el duplicado.

Todo lo demás es idempotente: evento repetido, reentrega de RabbitMQ y
publicación doble no crean notificaciones ni mails nuevos (pruebas de fallos
parciales, `pruebas/e2e/test_fallos_parciales.py`).

## Cambios para los diagramas

- **MER y modelo relacional:** NOTIFICACION suma `destinatario`, con
  `CHECK destinatario IN ('PACIENTE', 'PROFESIONAL')` y
  `UNIQUE (id_turno, tipo, destinatario)`.
- **Arquitectura:**
  - un contenedor nuevo, `reservas-publicador` (misma imagen que Reservas), que
    lee el outbox y publica en RabbitMQ: la flecha "publica evento" sale de él;
  - en RabbitMQ, la cola `notificaciones.turnos` y su DLQ
    (`turnos.dlx` → `notificaciones.turnos.dlq`);
  - la API de Reservas ya no habla con RabbitMQ: solo escribe el outbox.
