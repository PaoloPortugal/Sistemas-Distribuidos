# 006 — Copia de la franja en TURNO

**Estado:** aceptada.

## Contexto

Para aplicar el plazo de cancelación y para la agenda del profesional, reservas
necesita la fecha, el horario y el profesional de cada turno. En el modelo
relacional TURNO solo tiene `id_disponibilidad`; esos datos están en
DISPONIBILIDAD, que vive en catálogo. Ningún servicio accede a las tablas de
otro.

## Opciones consideradas

| | A. Consultar a catálogo cada vez | B. Copiarlos en TURNO al reservar |
| --- | --- | --- |
| Modelo relacional | Sin cambios | TURNO suma 4 columnas |
| Arquitectura | Más llamadas Reservas → Catálogo (y un endpoint interno más para la agenda) | Sin cambios |
| Si catálogo está caído | No se puede cancelar ni ver la agenda | Solo reservar depende de catálogo |
| Consistencia | Siempre al día | Puede quedar desactualizada si se edita una franja |

## Decisión

**Opción B.** Al reservar, reservas ya le pide a catálogo la franja para
validarla (`GET /interno/disponibilidades/{id}`); con esa misma respuesta
copia en TURNO:

- `email_profesional`
- `fecha`
- `horario_inicio`
- `horario_fin`

La copia es **solo para cancelar, ver la agenda y armar los eventos**: el dato
de verdad sigue siendo DISPONIBILIDAD en catálogo. `id_disponibilidad` sigue
siendo la referencia y la que usa el índice único parcial contra la doble
reserva.

## Cambios

- **Modelo relacional / MER:** TURNO (`id_turno`, `email_paciente`,
  `id_disponibilidad`, `id_servicio`, `estado`, `fecha_creacion`,
  `fecha_cancelacion`, `motivo_cancelacion`, `cancelado_por`,
  `email_profesional`, `fecha`, `horario_inicio`, `horario_fin`), con las
  cuatro últimas como copia desnormalizada. **Ya reflejado** en el MER (como
  atributos copiados) y en el PDF del modelo relacional; la arquitectura
  muestra la consulta Reservas → Catálogo al reservar.
- Los eventos `turno.confirmado` y `turno.cancelado` llevan esos datos
  (ADR 005), así notificaciones no necesita consultar a catálogo.

## Costo y consecuencia

- **La copia puede quedar desactualizada si una franja cambia.** Hoy no existe
  editar ni borrar disponibilidades, así que no puede pasar.
- **Si algún día se puede editar una franja, editar una franja con un turno
  RESERVADO tiene que estar prohibido.** Es la misma lógica que el
  `ON DELETE RESTRICT` de `TURNO.id_disponibilidad` en el modelo relacional:
  el turno ya se le comunicó al paciente con esa fecha y ese horario. Para
  cambiarlo, se cancela el turno (con su notificación) y se reserva otro.
  Cómo sabe catálogo si una franja tiene turno es parte del ADR 003.
- Una franja sin turnos sí se podría editar sin afectar ninguna copia.
