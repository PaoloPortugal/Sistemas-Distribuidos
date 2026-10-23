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
cp .env.example .env   # completar contraseñas
docker compose up --build
```

- Frontend: http://localhost:8080
- APIs: http://localhost:8080/api/usuarios, /api/catalogo-medicos, /api/reservas
- Swagger de cada servicio: `/api/<servicio>/docs`

## Estructura

```
servicios/      Un directorio por microservicio (código, Dockerfile, tests)
gateway/        Configuración de Traefik
frontend/       Cliente web mínimo (HTML + JS)
infra/          Scripts de PostgreSQL y observabilidad
pruebas/        Pruebas end-to-end y de concurrencia
docs/           Informe por secciones, ADRs y diagramas
```
