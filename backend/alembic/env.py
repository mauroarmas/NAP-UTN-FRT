from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from app.config import get_settings
from app.database import Base

# Importar TODOS los modelos para que Alembic los detecte
from app.models import (  # noqa: F401
    Usuario,
    Catedra,
    RecursoTemplate,
    Pedido,
    PedidoHistorial,
    Servicio,
    MetricaSnapshot,
)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Usar la URL de nuestra config, reemplazando asyncpg por psycopg2 para Alembic
settings = get_settings()
sync_url = settings.database_url.replace("+asyncpg", "")
config.set_main_option("sqlalchemy.url", sync_url)

# Metadata de nuestros modelos para autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
