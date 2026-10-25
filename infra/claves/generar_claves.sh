#!/bin/sh
# Genera el par de claves RSA de desarrollo para firmar los JWT (RS256).
#   secretos/jwt_privada.pem  -> solo la monta el servicio usuarios
#   secretos/jwt_publica.pem  -> la usan los servicios que validan tokens
# Uso: sh infra/claves/generar_claves.sh [--forzar]
set -eu

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
DIRECTORIO="$RAIZ/secretos"
PRIVADA="$DIRECTORIO/jwt_privada.pem"
PUBLICA="$DIRECTORIO/jwt_publica.pem"

if [ -e "$PRIVADA" ] && [ "${1:-}" != "--forzar" ]; then
  echo "Las claves ya existen en $DIRECTORIO. Usá --forzar para regenerarlas"
  echo "(los tokens emitidos con la clave anterior dejan de ser válidos)."
  exit 0
fi

mkdir -p "$DIRECTORIO"
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$PRIVADA"
openssl pkey -in "$PRIVADA" -pubout -out "$PUBLICA"
chmod 600 "$PRIVADA"
chmod 644 "$PUBLICA"

echo "Claves generadas en $DIRECTORIO"
