"""Hash y verificación de contraseñas con argon2."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()

# Se verifica contra este hash cuando el email no existe, para que el tiempo
# de respuesta del login no revele qué emails están registrados.
_HASH_FICTICIO = _hasher.hash("contrasena-ficticia-para-igualar-tiempos")


def hashear(contrasena: str) -> str:
    return _hasher.hash(contrasena)


def verificar(hash_guardado: str | None, contrasena: str) -> bool:
    """Indica si la contraseña corresponde al hash; None cuenta como inválido."""
    try:
        _hasher.verify(hash_guardado or _HASH_FICTICIO, contrasena)
    except (VerificationError, InvalidHashError):
        return False
    return hash_guardado is not None
