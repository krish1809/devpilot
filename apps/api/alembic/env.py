from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  (registers ORM models on Base.metadata)
from alembic import context
from app.core.config import get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()

config.set_main_option(
    "sqlalchemy.url",
    settings.database_url,
)

target_metadata = Base.metadata

# Tables owned by LangGraph's PostgresSaver (created by its own `setup()`), not
# by our models. Without this, autogenerate would propose dropping them.
_EXTERNAL_TABLES = {
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
}


def include_object(object, name, type_, reflected, compare_to):  # noqa: A002
    return not (type_ == "table" and reflected and name in _EXTERNAL_TABLES)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""

    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
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
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
    # LangGraph's checkpoint tables (managed by the library, outside a
    # transaction because it uses CREATE INDEX CONCURRENTLY). Skipped for
    # autogenerate/check runs and downgrades.
    if not getattr(config.cmd_opts, "autogenerate", False) and "downgrade" not in str(
        getattr(config.cmd_opts, "cmd", "")
    ):
        from app.agents.checkpoint import setup_checkpoint_tables

        setup_checkpoint_tables(settings.database_url)
