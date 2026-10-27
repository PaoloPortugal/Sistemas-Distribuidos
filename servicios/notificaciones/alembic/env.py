from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import configuracion
from app.db.modelos import Base, ESQUEMA

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def incluir_nombre(nombre, tipo, objetos_padre):
    if tipo == "schema":
        return nombre == ESQUEMA
    return True


opciones = {
    "target_metadata": target_metadata,
    "version_table_schema": ESQUEMA,
    "include_schemas": True,
    "include_name": incluir_nombre,
    "compare_type": True,
}


def correr_migraciones_offline():
    context.configure(
        url=configuracion.url_base_datos,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **opciones,
    )
    with context.begin_transaction():
        context.run_migrations()


def correr_migraciones_online():
    motor = create_engine(
        configuracion.url_base_datos,
        poolclass=pool.NullPool,
        connect_args={"options": "-c search_path=public"},
    )
    with motor.connect() as conexion:
        context.configure(connection=conexion, **opciones)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    correr_migraciones_offline()
else:
    correr_migraciones_online()
