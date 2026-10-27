# Metodología Twelve-Factor

Factores aplicados en el proyecto y cómo.

| Factor | Cómo se aplica |
| --- | --- |
| I. Código base | Un repositorio con un directorio por servicio en `servicios/`, versionado en Git; cada cambio entra por rama y pull request. |
| II. Dependencias | Cada servicio declara sus dependencias en `requirements.txt` y se instalan en su imagen de Docker. Las versiones todavía no están fijadas. |
| III. Configuración | Toda la configuración se lee de variables de entorno (pydantic-settings): URL de la base, URL de Catálogo, timeouts, zona horaria, duración del token. `.env.example` documenta las variables; `.env` y las claves JWT no se suben al repositorio. Cada contenedor recibe solo sus propias variables. |
| IV. Servicios de respaldo | PostgreSQL, RabbitMQ y el servidor de correo se conectan por URL o host configurables; cambiar Mailpit por un SMTP real es cambiar una variable. |
| V. Construcción, publicación, ejecución | Cada servicio se construye como imagen de Docker (`docker compose build`) y se ejecuta con la configuración del entorno. |
| VI. Procesos | Los servicios no guardan estado en memoria: los datos están en PostgreSQL y la sesión del usuario viaja en el JWT. |
| VII. Asignación de puertos | Cada servicio expone su propio puerto HTTP con uvicorn (8001 a 8004) y el gateway los publica bajo un único puerto. |
| VIII. Concurrencia | El trabajo se reparte en tipos de proceso: la API de Reservas atiende pedidos y el Publicador (misma imagen, otro comando) envía los eventos del outbox. Cada tipo escala por separado, y varios publicadores pueden correr a la vez porque toman eventos con `FOR UPDATE SKIP LOCKED`. |
| IX. Desechabilidad | Los contenedores arrancan rápido y esperan a sus dependencias con healthchecks. En Usuarios, Catálogo y Reservas uvicorn corre con `exec`, para recibir las señales de parada. |
| X. Paridad entre entornos | Todos los integrantes levantan las mismas imágenes con `docker compose`; la diferencia con producción se limita a servicios de respaldo configurables (Mailpit). |
| XII. Procesos de administración | Las migraciones de Alembic y la carga de datos iniciales corren con el mismo código e imagen que la aplicación, al arrancar el contenedor ([ADR 001](decisiones/001-migraciones-al-arrancar.md)). |

<!-- Pendiente: XI (logs como flujo de eventos a stdout), cuando se
implemente la observabilidad. -->
