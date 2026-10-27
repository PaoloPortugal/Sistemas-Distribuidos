# Sistema distribuido de gestión de turnos médicos

Proyecto de Sistemas Distribuidos — Universidad de Montevideo.

## Arquitectura

| Componente | Tecnología | Puerto local |
| --- | --- | --- |
| API Gateway | Traefik | 8080 (panel: 8081) |
| Usuarios | FastAPI | interno 8001 |
| Catálogo de médicos | FastAPI | interno 8002 |
| Reservas | FastAPI | interno 8003 |
| Notificaciones (worker) | Python + aio-pika | interno 8004 |
| Base de datos | PostgreSQL 16 (un esquema por servicio) | 5433 (`PUERTO_POSTGRES`) |
| Mensajería | RabbitMQ (exchange `turnos`) | panel: 15672 |
| Correo (desarrollo) | Mailpit | 8025 |

## Cómo levantarlo

```bash
cp .env.example .env              # completar contraseñas
sh infra/claves/generar_claves.sh # claves JWT de desarrollo (una sola vez)
docker compose up --build
```

- Frontend React: http://localhost:8080
- APIs: http://localhost:8080/api/usuarios, /api/catalogo-medicos, /api/reservas
- Swagger de cada servicio: `/api/<servicio>/docs`

### Datos de demo

Con los servicios levantados, se pueden crear profesionales, especialidades y
horarios de ejemplo usando las APIs del gateway:

```bash
./scripts/sembrar_demo.sh
```

El script crea cinco profesionales de Clínica médica, Pediatría, Cardiología y
Dermatología, con horarios durante los próximos días hábiles. Se puede ejecutar
más de una vez: los profesionales y horarios que ya existan se omiten.

En el frontend, esos profesionales ingresan desde la pestaña **Profesional**.
Su pantalla **Horarios** permite consultar la agenda por día, crear y eliminar
disponibilidades. **Modificar** un horario lo elimina y crea otro con los
datos nuevos (ADR 003); si el horario no se puede eliminar, no se crea el
nuevo. Los horarios que ya tienen una consulta reservada se muestran como
**Agendado**: el backend no deja eliminarlos (409) hasta que se cancele el
turno.

Los pacientes solo ven los horarios libres. Los avisos de confirmación y
cancelación llegan por mail; en desarrollo se ven en Mailpit
(http://localhost:8025).

La contraseña compartida de los profesionales de demo es
`DemoTurnos2026!`. Se puede cambiar sin editar el script:

```bash
DEMO_CONTRASENA='otra-clave-segura' ./scripts/sembrar_demo.sh
```

Para usar otro gateway:

```bash
BASE_URL='http://localhost:9000' ./scripts/sembrar_demo.sh
```

### Extensiones de PostgreSQL

`catalogo_medicos` necesita la extensión `btree_gist` para impedir
disponibilidades superpuestas. Los usuarios de los servicios no pueden crearla,
así que la crea `infra/postgres/init/02-extensiones.sh` como superusuario.

Ese script solo corre al inicializar un volumen vacío. Si tu base ya estaba
inicializada, la migración de catálogo falla avisando que falta la extensión.
Hay dos caminos:

```bash
# Crearla a mano (no borra datos)
docker compose exec postgres psql -U postgres -d turnos -c "CREATE EXTENSION IF NOT EXISTS btree_gist"

# o recrear la base desde cero (borra todos los datos)
docker compose down -v
```

Si cambiaste `POSTGRES_USER` o `POSTGRES_DB` en `.env`, usá esos valores en
lugar de `postgres` y `turnos`.

### Claves JWT de desarrollo

El servicio `usuarios` firma los tokens con RS256: firma con una clave privada
y los demás servicios los validan con la clave pública. Para generar el par:

```bash
sh infra/claves/generar_claves.sh
```

- Crea `secretos/jwt_privada.pem` y `secretos/jwt_publica.pem`. En Windows se
  corre desde Git Bash, que trae `openssl`.
- Si las claves ya existen no las pisa. Para regenerarlas se usa `--forzar`;
  los tokens emitidos con la clave anterior dejan de ser válidos.
- `secretos/` está en `.gitignore`: **la clave privada no se sube a git**.
  Cada integrante genera su propio par.
- Docker Compose las monta como *secrets* en `/run/secrets/`: `usuarios`
  recibe la privada y la pública; `catalogo-medicos` y `reservas`, solo la
  pública. Si no existen, `docker compose up` falla avisando que falta el
  archivo.

## Estructura

```
servicios/      Un directorio por microservicio (código, Dockerfile, tests)
gateway/        Configuración de Traefik
frontend/      Cliente web React estático (Babel en el navegador + Nginx)
infra/          Scripts de PostgreSQL y observabilidad
pruebas/        Pruebas end-to-end y de concurrencia
docs/           Informe por secciones, ADRs y diagramas
```
