# Persistencia y modelo de datos

Una instancia de PostgreSQL 16 con un esquema y un usuario por servicio: cada
servicio es dueño de sus tablas y ninguno accede a las de otro. Los datos
persisten entre reinicios en el volumen `datos_postgres`.

- MER: [mer.drawio.png](diagramas/mer.drawio.png) (editable:
  [mer.drawio](diagramas/mer.drawio))
- Modelo relacional y restricciones:
  [modelo-relacional.pdf](diagramas/modelo-relacional.pdf) (editable:
  [modelo-relacional.docx](diagramas/modelo-relacional.docx))

## Tablas por servicio

| Servicio | Esquema | Tablas del MER | Tablas técnicas |
| --- | --- | --- | --- |
| Usuarios | `usuarios` | USUARIO, PACIENTE | `alembic_version` |
| Catálogo | `catalogo_medicos` | ESPECIALIDAD, PROFESIONAL, SERVICIO, DISPONIBILIDAD | `alembic_version` |
| Reservas | `reservas` | TURNO | `evento_saliente` (outbox, [ADR 005](decisiones/005-outbox-eventos-turno.md)), `alembic_version` |
| Notificaciones | `notificaciones` | NOTIFICACION | — |

El script `infra/postgres/init/01-esquemas.sh` crea los esquemas y usuarios, y
`02-extensiones.sh` crea la extensión `btree_gist`. Los dos corren solo al
inicializar un volumen vacío.

## Restricciones implementadas en la base

| Regla | Implementación |
| --- | --- |
| Un solo turno activo por horario | Índice único parcial `UNIQUE (id_disponibilidad) WHERE estado = 'RESERVADO'` |
| Horarios de un profesional sin superposición | `EXCLUDE USING gist` sobre el email del profesional y el rango horario |
| Inicio anterior al fin | `CHECK (horario_inicio < horario_fin)` |
| Datos de cancelación solo en turnos cancelados | `CHECK` sobre estado, fecha_cancelacion y cancelado_por |
| Cancelación posterior a la creación | `CHECK (fecha_cancelacion >= fecha_creacion)` |
| Dominios de tipo, estado y cancelado_por | `CHECK ... IN (...)` |
| Emails en minúsculas | `CHECK (email = lower(email))` en USUARIO, PROFESIONAL y TURNO |
| Claves candidatas | `UNIQUE` en documento, matrícula, nombre de especialidad, (especialidad, nombre) del servicio y (profesional, fecha, inicio) del horario |
| FK dentro de un mismo servicio | `FOREIGN KEY` con `CASCADE` o `RESTRICT` según el modelo relacional |

Las reglas que cruzan servicios (FK hacia otro esquema, especialización
total, coherencia del servicio) no las puede validar el motor; cómo se
garantiza cada una está en el modelo relacional y en
[02-caracteristicas-sd.md](02-caracteristicas-sd.md).

## Copias entre servicios

| Copia | De dónde viene | Para qué | ADR |
| --- | --- | --- | --- |
| PROFESIONAL.nombre, apellido | USUARIO | Listar profesionales sin consultar a Usuarios | [004](decisiones/004-copia-nombre-profesional.md) |
| TURNO.email_profesional, fecha, horario_inicio, horario_fin | DISPONIBILIDAD | Cancelar, ver la agenda y armar los avisos sin consultar a Catálogo | [006](decisiones/006-copia-franja-en-turno.md) |

## Migraciones

Cada servicio versiona su esquema con Alembic, y el contenedor aplica las
migraciones pendientes antes de levantar la API: si fallan, no arranca
([ADR 001](decisiones/001-migraciones-al-arrancar.md)). Las especialidades y
servicios se cargan con una migración de datos iniciales (4 especialidades, 10
servicios).

| Servicio | Migraciones |
| --- | --- |
| Usuarios | `0001` USUARIO y PACIENTE |
| Catálogo | `0001` tablas, `0002` datos iniciales, `0003` nombre y apellido en PROFESIONAL |
| Reservas | `0001` TURNO y outbox |

<!-- Pendiente: tablas de notificaciones (NOTIFICACION y sus tablas técnicas)
cuando se implemente el servicio. -->
