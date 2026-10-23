"""Entorno de Alembic del servicio de usuarios.

La URL sale de la configuración (URL_BASE_DATOS) y Alembic solo mira el
esquema `usuarios`, donde también guarda su tabla de versiones.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import configuracion
from app.db.modelos import ESQUEMA, Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def incluir_nombre(nombre, tipo, objetos_padre):
    """Limita la comparación de autogenerate al esquema propio del servicio."""
    if tipo == "schema":
        return nombre == ESQUEMA
    return True


opciones_contexto = {
    "target_metadata": target_metadata,
    "version_table_schema": ESQUEMA,
    "include_schemas": True,
    "include_name": incluir_nombre,
    "compare_type": True,
}


def correr_migraciones_offline() -> None:
    context.configure(
        url=configuracion.url_base_datos,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **opciones_contexto,
    )
    with context.begin_transaction():
        context.run_migrations()


def correr_migraciones_online() -> None:
    # El rol tiene search_path=usuarios; con ese valor PostgreSQL informa las
    # FK y la tabla de versiones sin esquema y autogenerate ve diferencias
    # falsas. Como modelos y migraciones nombran el esquema explícitamente,
    # Alembic se conecta con search_path=public.
    motor = create_engine(
        configuracion.url_base_datos,
        poolclass=pool.NullPool,
        connect_args={"options": "-c search_path=public"},
    )
    with motor.connect() as conexion:
        context.configure(connection=conexion, **opciones_contexto)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    correr_migraciones_offline()
else:
    correr_migraciones_online()
