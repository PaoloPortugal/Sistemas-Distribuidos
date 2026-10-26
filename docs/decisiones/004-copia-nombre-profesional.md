# 004 — Copia de nombre y apellido en PROFESIONAL

**Estado:** aceptada.

## Contexto

`GET /profesionales` de catálogo tiene que mostrar nombre y apellido de cada
profesional. En el modelo relacional original, PROFESIONAL tenía solo `email`,
`matricula` e `id_especialidad`; nombre y apellido están en USUARIO, que vive
en el servicio de usuarios. Ningún servicio accede a las tablas de otro.

## Opciones consideradas

| | A. Copiarlos en el alta interna | B. Catálogo consulta a usuarios por REST | C. El cliente web los combina |
| --- | --- | --- | --- |
| Diagrama de arquitectura | Sin flechas nuevas: reutiliza Usuarios → Catálogo (ADR 002) | Agrega Catálogo → Usuarios | Sin flechas nuevas entre servicios |
| Modelo relacional | PROFESIONAL suma `nombre` y `apellido` | Sin cambios | Sin cambios |
| Si usuarios está caído | El listado funciona | El listado falla o sale sin nombres | El listado sale sin nombres |
| Consistencia | Puede quedar desactualizada | Siempre al día | Siempre al día |

## Decisión

**Opción A.** El servicio de usuarios manda `nombre` y `apellido` en
`POST /interno/profesionales` y catálogo los guarda en PROFESIONAL
(migración `0003`). La copia es **solo para mostrar**: el dato de verdad
sigue siendo USUARIO.nombre y USUARIO.apellido.

Motivos: el listado de profesionales es la consulta más frecuente del sistema
y así no depende de que usuarios esté disponible; además no agrega
comunicación nueva entre servicios.

## Cambios

- **Modelo relacional:** PROFESIONAL (`email`, `matricula`, `id_especialidad`,
  `nombre`, `apellido`), con nombre y apellido como copia desnormalizada.
  **Ya reflejado** en el MER (como atributos copiados) y en el PDF del modelo
  relacional.
- **Contrato** (`docs/05-comunicacion.md`): el POST interno exige `nombre` y
  `apellido`. Un reintento con la misma matrícula y especialidad responde
  200 y actualiza la copia si cambió.
- **Usuarios:** el cliente de catálogo manda los dos campos.

## Costo

- **La copia puede quedar desactualizada.** Hoy no existe la edición de
  nombre o apellido, así que no pasa. Cuando exista, `usuarios` tendrá que
  avisarle a catálogo: con una llamada interna (por ejemplo
  `PATCH /interno/profesionales/{email}`) o publicando un evento
  `usuario.modificado` que catálogo consuma. La segunda opción agrega
  RabbitMQ → Catálogo al diagrama.
- Mientras tanto, si llegara a haber una diferencia, lo que se muestra en el
  catálogo es lo que tenía USUARIO al momento del alta.
- Las filas de PROFESIONAL anteriores a la migración `0003` quedan con
  nombre y apellido vacíos (no debería haber ninguna real todavía).
