# Instrucciones para agentes de IA

## Fuentes de verdad
- Modelo relacional y restricciones: docs/diagramas/Modelo relacional y restricciones de integridad.pdf
- MER: docs/diagramas/MER_turnos_clinica_v2.drawio.png
- Arquitectura: docs/diagramas/Arquitectura_turnos_clinica.drawio.png
Todo cambio debe ser coherente con estas fuentes. Si algo no coincide, avisar antes de implementar.

## Contexto
Sistema distribuido de gestión de turnos médicos (proyecto académico).
Stack: Python 3.12 + FastAPI, PostgreSQL, RabbitMQ, Traefik, Docker Compose, pytest.

## Principios
- Un servicio por responsabilidad: usuarios, catalogo_medicos, reservas, notificaciones.
- Ningún servicio accede a las tablas de otro; se comunican por REST o por eventos.
- Reservas es la autoridad final: la doble reserva se impide con restricciones en PostgreSQL.
- Eventos en el exchange `turnos`: turno.confirmado y turno.cancelado. No existe
  turno.modificado: modificar un turno es cancelarlo y reservar otro.
- Consumidores idempotentes (registrar los event_id procesados).
- Configuración solo por variables de entorno; nunca secretos en el repositorio.
- Logs JSON a stdout con correlation_id.
- Lógica de negocio en `app/dominio`, endpoints en `app/api`, persistencia en `app/db`.
- Código, nombres y comentarios en español.

## Forma de trabajo
Proponer un plan antes de modificar archivos, implementar solo lo pedido,
correr las pruebas relevantes y no afirmar que se ejecutó una prueba si no se ejecutó.
