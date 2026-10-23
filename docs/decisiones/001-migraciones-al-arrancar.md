# 001 — Migraciones al arrancar el contenedor

**Estado:** pendiente de revisar antes de escalar a varias réplicas.

## Contexto

El servicio `usuarios` ejecuta `alembic upgrade head` en el `CMD` de su
Dockerfile, antes de levantar uvicorn. Con una sola réplica es simple y
garantiza que el esquema esté al día cuando la API empieza a atender.

## Problema pendiente

Si se levantan varias réplicas del mismo servicio (por ejemplo
`docker compose up --scale usuarios=3`), todas correrían las migraciones al
mismo tiempo. Alembic no coordina ejecuciones concurrentes: dos réplicas
pueden intentar aplicar la misma revisión y una de ellas fallaría (por
ejemplo, con "relation already exists") y no arrancaría.

## Opciones a evaluar

1. **Servicio de migración separado:** un contenedor de una sola ejecución
   (`usuarios-migraciones`) que corre `alembic upgrade head`, y las réplicas
   de la API dependen de él con `depends_on: condition: service_completed_successfully`.
2. **Bloqueo en PostgreSQL:** tomar `pg_advisory_lock` en `alembic/env.py`
   antes de migrar, para que una réplica migre y las demás esperen.
3. **Migrar como paso del despliegue:** sacar la migración del arranque y
   ejecutarla a mano o desde CI antes de actualizar las réplicas.

## Decisión

Por ahora se mantiene la migración en el arranque (una réplica). Revisar
esta decisión antes de escalar cualquier servicio que use este patrón.
