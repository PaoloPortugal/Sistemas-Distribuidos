# Uso de inteligencia artificial

Registro de las tareas en las que se usó IA como herramienta de apoyo y de las decisiones a las que contribuyó. Las decisiones finales las tomó el equipo.

## Diagrama de arquitectura (AOD)

Se usó la IA para generar borradores del diagrama de arquitectura y para discutir alternativas antes de dibujar la versión del equipo. El diagrama final lo dibujó el equipo.

Decisiones en las que sirvió de apoyo:

- Clasificar la arquitectura como microservicios con comunicación síncrona por REST y eventos asíncronos por RabbitMQ, en lugar de una arquitectura event-driven completa o microservicios completa.
- Comparar dos variantes para la autenticación: un servicio de Auth separado de Usuarios, o un único servicio que reúne ambos. Se eligió el servicio único para que el registro sea una transacción local y no una operación distribuida.

Aclaración posterior: el registro de pacientes sigue siendo una transacción local en Usuarios. El de profesionales no, porque el equipo decidió que PROFESIONAL viva en el servicio de Catálogo: Usuarios llama por REST a Catálogo y, si no puede confirmar, compensa borrando el profesional creado. La decisión y sus consecuencias están en [ADR 002](decisiones/002-registro-profesional-compensacion.md); el diagrama de arquitectura se actualiza para agregar esa comunicación.

## Esqueleto del proyecto

Se usó la IA para crear la estructura inicial del repositorio a partir del stack elegido (Python + FastAPI, PostgreSQL, RabbitMQ, Traefik, Docker Compose).

Lo que generó la IA:

- La estructura de carpetas: un directorio por servicio en `servicios/` (con `app/api`, `app/dominio`, `app/db` y `tests`), además de `gateway/`, `frontend/`, `infra/`, `pruebas/` y `docs/`.
- Un `Dockerfile`, un `requirements.txt` y un endpoint `/salud` con su prueba para cada servicio.
- Un `docker-compose.yml` con el gateway, PostgreSQL, RabbitMQ, Mailpit y los cuatro servicios.
- Un script de inicialización de PostgreSQL que crea un esquema y un usuario por servicio.
- `.env.example`, `.gitignore`, `README.md` y `CLAUDE.md` con las convenciones del proyecto.

Verificación: se ejecutó la prueba de salud de cada servicio y se comprobó que `docker-compose.yml` es válido. Al momento de este registro, todavía no se levantó el sistema completo con Docker.
