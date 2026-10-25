# 002 — Registro de profesional con compensación

**Estado:** aceptada. El endpoint de catálogo (`/interno/profesionales`) está
pendiente; hasta que exista, `/registro/profesional` responde 503 y no crea nada.

## Contexto

El MER define la especialización de USUARIO como **total y disjunta**: todo
USUARIO de tipo PROFESIONAL tiene que existir en PROFESIONAL (email,
matrícula UNIQUE, id_especialidad NOT NULL → ESPECIALIDAD).

El equipo decidió que PROFESIONAL viva en el esquema de `catalogo_medicos`,
porque catálogo lo necesita para listar y filtrar profesionales por
especialidad, y que USUARIO siga en `usuarios`.

## Por qué no hay FK ni transacción entre servicios

Cada servicio es dueño de su esquema y ninguno accede a las tablas de otro
(CLAUDE.md). PostgreSQL solo valida FK y transacciones dentro de lo que una
conexión ve: `usuarios` no puede declarar una FK hacia
`catalogo_medicos.profesional` ni confirmar las dos inserciones en una misma
transacción. Una transacción distribuida (two-phase commit) acoplaría los
servicios y los bloquearía entre sí ante fallas, así que la especialización
total se garantiza desde la aplicación.

Por la misma razón, el `ON DELETE CASCADE` de PROFESIONAL.email → USUARIO del
modelo relacional no lo puede aplicar la base: cuando exista el borrado de
usuarios, tendrá que llamar a `DELETE /interno/profesionales/{email}`.

## Decisión: flujo con compensación

En `app/dominio/usuarios.py` (`registrar_profesional`):

1. Insertar el USUARIO (tipo PROFESIONAL) con `flush`, sin commit. Si el email
   ya existe (como paciente o profesional), PostgreSQL lo rechaza → **409**, sin
   llamar a catálogo. Esto también garantiza que la especialización sea
   disjunta.
2. Pedirle a catálogo que cree el PROFESIONAL (`POST /interno/profesionales`,
   timeout corto).
3. Si catálogo responde OK → commit del USUARIO.
4. Si catálogo responde con error o no responde → rollback: el USUARIO no queda.
   - Matrícula duplicada → **409**; especialidad inexistente → **422**.
   - Caído, timeout o respuesta fuera del contrato → **503**.
   - Si el pedido pudo haberse aplicado igual (timeout de lectura, conexión
     cortada, 5xx), además se compensa con `DELETE`.
5. Si catálogo creó el PROFESIONAL pero el commit en `usuarios` falla →
   compensar con `DELETE /interno/profesionales/{email}` y responder **503**.

Las dos operaciones de catálogo son idempotentes por email, así que compensar
"por las dudas" o reintentar el registro es seguro. El contrato está en
[05-comunicacion.md](../05-comunicacion.md).

## Inconsistencias temporales posibles

- **Profesional huérfano:** si falla el commit en `usuarios` (o hubo timeout) y
  además falla la compensación, queda un PROFESIONAL en catálogo sin USUARIO.
  Se registra en el log con el texto "Inconsistencia". No rompe la
  especialización total (no hay USUARIO PROFESIONAL sin PROFESIONAL), pero
  catálogo podría listar a alguien que no puede iniciar sesión.
  - Si la persona reintenta con los **mismos datos**, catálogo responde 200
    (idempotente), se confirma el USUARIO y la inconsistencia se repara sola.
  - Si reintenta con **otros datos**, catálogo responde
    `EMAIL_CON_OTROS_DATOS` y `usuarios` devuelve 409 hasta que se borre el
    huérfano.
- **Ventana entre los pasos 2 y 3:** durante la llamada a catálogo, el
  PROFESIONAL ya existe y el USUARIO todavía no está confirmado. Un listado de
  catálogo en ese momento puede mostrar al profesional antes de que pueda
  iniciar sesión. Dura como máximo el timeout.
- **Lock durante la llamada:** el insert del USUARIO sin confirmar bloquea ese
  email en PostgreSQL mientras se espera a catálogo. Un registro simultáneo con
  el mismo email espera y después recibe 409. El timeout corto acota la espera.

## Pendientes

- **Protección de `/interno`:** hoy Traefik no publica esas rutas (regla con
  `!PathPrefix`), pero cualquier contenedor de la red de Docker puede llamarlas.
  Falta autenticación entre servicios (por ejemplo, un token interno en un
  secret, o mTLS).
- **Reconciliación de huérfanos:** un proceso que compare PROFESIONAL con
  USUARIO y borre los profesionales sin usuario, o reintentar la compensación
  desde una cola en lugar de solo registrarla en el log.
- **Diagrama de arquitectura:** agregar la comunicación REST Usuarios → Catálogo
  (lo actualiza el equipo).
