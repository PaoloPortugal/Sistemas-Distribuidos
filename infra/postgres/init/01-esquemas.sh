#!/bin/bash
# Crea un esquema y un usuario por servicio (cada servicio es dueño de sus datos).
set -e
for svc in usuarios catalogo_medicos reservas notificaciones; do
  var_usuario="${svc^^}_DB_USUARIO"
  var_contrasena="${svc^^}_DB_CONTRASENA"
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<-SQL
    CREATE USER ${!var_usuario} WITH PASSWORD '${!var_contrasena}';
    CREATE SCHEMA ${svc} AUTHORIZATION ${!var_usuario};
    ALTER ROLE ${!var_usuario} SET search_path TO ${svc};
SQL
done
