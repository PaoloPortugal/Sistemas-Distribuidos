# 009 — Nombres de los pacientes en la agenda

**Estado:** aceptada e implementada. **Cambia la arquitectura** (flecha
Reservas → Usuarios); el MER y el modelo relacional no cambian.

## Contexto

El frontend del profesional muestra en la agenda el nombre de cada paciente.
TURNO solo tiene `email_paciente`; el nombre y el apellido están en USUARIO,
en el servicio de usuarios, y ningún servicio accede a las tablas de otro.

## Opciones consideradas

| | A. Reservas consulta a usuarios al armar la agenda | B. Copiar nombre y apellido en TURNO al reservar |
| --- | --- | --- |
| Modelo relacional | Sin cambios | TURNO suma 2 columnas (copia, como el ADR 004) |
| Arquitectura | Flecha Reservas → Usuarios | Sin flecha nueva si los datos van en el token; si no, igual hay que consultar a usuarios al reservar |
| Si usuarios está caído | La agenda sale sin nombres | La agenda tiene los nombres |
| Consistencia | Siempre al día | La copia queda vieja si el paciente cambia su nombre |
| Turnos ya existentes | Muestran el nombre | Quedan sin nombre (no hay de dónde copiarlo) |

## Decisión

**Opción A**, que es la que trajo el frontend del profesional (PR #15), con
tres correcciones:

1. **La agenda no depende de usuarios.** Si usuarios no responde, responde
   algo fuera del contrato o no conoce a un paciente, la agenda sale igual con
   `nombre_paciente` y `apellido_paciente` en `null`. Antes respondía 500.
2. **Una sola llamada por agenda.** `POST /interno/usuarios/nombres` recibe
   los emails de todos los pacientes de la agenda (hasta 1000, sin repetir) y
   devuelve los que existen. Antes había una llamada por paciente.
3. **Límite de tiempo total.** El timeout de httpx no cubre la resolución DNS
   (con el contenedor de usuarios detenido, resolver su nombre tarda unos
   8 s). El pedido corre en un hilo y se espera como máximo
   `TIMEOUT_USUARIOS_SEGUNDOS` (3 s), el mismo mecanismo que el cliente de
   catálogo → reservas (ADR 003).

Los campos de nombre van en `TurnoEnAgenda`, solo en `GET /agenda`;
`POST /turnos`, `GET /mis-turnos` y cancelar no cambian.

Usuarios también expone `GET /interno/usuarios/{email}` (un solo usuario;
404 `USUARIO_INEXISTENTE` si no existe). Reservas no lo usa.

Ninguno devuelve datos sensibles: solo email, nombre y apellido. Traefik no
publica `/api/usuarios/interno`.

## Consecuencias

- **Arquitectura:** flecha nueva **Reservas → Usuarios** (REST interno),
  solo para la agenda. Reservar, cancelar y "mis turnos" siguen sin depender
  de usuarios.
- **Degradación:** con usuarios caído, el profesional ve sus turnos con el
  email del paciente en lugar del nombre.
- Si en algún momento los nombres tienen que estar aunque usuarios esté
  caído, se puede pasar a la opción B.
