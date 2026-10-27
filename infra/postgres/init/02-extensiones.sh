#!/bin/bash
# Extensiones que los usuarios de los servicios no pueden crear (requieren superusuario).
#   btree_gist: catalogo_medicos la usa para impedir disponibilidades superpuestas
#               (EXCLUDE USING gist sobre email_profesional y el rango horario).
# Solo corre al inicializar un volumen vacío. Con una base ya inicializada:
#   docker compose exec postgres psql -U postgres -d turnos -c "CREATE EXTENSION IF NOT EXISTS btree_gist"
set -e
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<-SQL
    CREATE EXTENSION IF NOT EXISTS btree_gist;
SQL
