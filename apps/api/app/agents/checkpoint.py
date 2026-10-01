"""Durable LangGraph checkpoints in the app's PostgreSQL database.

The checkpoint tables (``checkpoints``, ``checkpoint_blobs``,
``checkpoint_writes``, ``checkpoint_migrations``) are owned and migrated by
LangGraph's ``PostgresSaver.setup()``, not by our models. ``alembic upgrade
head`` calls ``setup_checkpoint_tables`` after our migrations (see
``alembic/env.py``), so it runs once at deploy time.

Never call ``setup()`` lazily from a request: it issues ``CREATE INDEX
CONCURRENTLY``, which waits for every open transaction — including the
request's own DB session — and deadlocks.
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from sqlalchemy.engine import make_url

from app.core.config import get_settings


def psycopg_conninfo(database_url: str) -> str:
    """SQLAlchemy URL (postgresql+psycopg://…) → libpq conninfo for psycopg."""
    return make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)


def setup_checkpoint_tables(database_url: str) -> None:
    """Create/upgrade LangGraph's checkpoint tables (idempotent)."""
    with PostgresSaver.from_conn_string(psycopg_conninfo(database_url)) as saver:
        saver.setup()


def make_postgres_checkpointer(database_url: str, *, max_size: int = 5) -> PostgresSaver:
    pool = ConnectionPool(
        psycopg_conninfo(database_url),
        min_size=1,
        max_size=max_size,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    return PostgresSaver(pool)


@lru_cache
def get_postgres_checkpointer() -> PostgresSaver:
    return make_postgres_checkpointer(get_settings().database_url)


if __name__ == "__main__":  # python -m app.agents.checkpoint
    setup_checkpoint_tables(get_settings().database_url)
    print("LangGraph checkpoint tables are up to date.")
