# Definición: problemática, alcance y actores

## Problemática

En una clínica médica privada, los pacientes necesitan consultar rápido qué
profesionales atienden, en qué horarios, y reservar una consulta. Los
profesionales necesitan administrar su disponibilidad y ver su agenda.

## Solución propuesta

Un sistema distribuido de gestión y reserva de turnos, formado por servicios
independientes que se comunican por REST y por mensajería asíncrona. Permite:

- a los **pacientes**: registrarse, consultar profesionales por especialidad y
  sus horarios, reservar y cancelar turnos, y recibir notificaciones de sus
  turnos;
- a los **profesionales**: registrarse con su matrícula y especialidad, cargar
  sus horarios, ver su agenda y cancelar turnos.

Modificar un turno equivale a cancelarlo y reservar otro
([ADR 007](decisiones/007-cancelacion-y-estados-de-turno.md)).

## Actores

| Actor | Qué hace en el sistema |
| --- | --- |
| Paciente | Se registra, consulta profesionales y horarios, reserva, consulta y cancela sus turnos (hasta 24 h antes del inicio). |
| Profesional | Se registra con matrícula y especialidad, carga sus horarios, consulta su agenda y cancela turnos (hasta el inicio). |
| Sistema de correo | Recibe los avisos de confirmación y cancelación. En desarrollo es Mailpit. |

No hay rol administrador: las especialidades y los servicios de la clínica se
cargan como datos iniciales.

## Alcance

Incluye la gestión de pacientes, profesionales, especialidades, servicios,
disponibilidad, turnos y notificaciones.

Queda fuera de alcance: historias clínicas, diagnósticos, recetas, pagos,
gestión de seguros y el estado FINALIZADO automático de los turnos
([ADR 007](decisiones/007-cancelacion-y-estados-de-turno.md)).

## Por qué un sistema distribuido

El dominio trae los problemas que el proyecto busca resolver: dos pacientes
que reservan el mismo horario a la vez (concurrencia), datos repartidos entre
servicios que tienen que seguir siendo coherentes (consistencia), y avisos que
no se pueden perder aunque falle un componente (tolerancia a fallos).
