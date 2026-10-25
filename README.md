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

- Frontend: http://localhost:8080
- APIs: http://localhost:8080/api/usuarios, /api/catalogo-medicos, /api/reservas
- Swagger de cada servicio: `/api/<servicio>/docs`

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
frontend/       Cliente web mínimo (HTML + JS)
infra/          Scripts de PostgreSQL y observabilidad
pruebas/        Pruebas end-to-end y de concurrencia
docs/           Informe por secciones, ADRs y diagramas
```
