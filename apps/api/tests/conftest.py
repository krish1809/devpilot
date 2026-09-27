"""Pytest fixtures backed by a dedicated PostgreSQL test database.

The test database is created from scratch for the session and dropped at the
end. Tables are created directly from the SQLAlchemy metadata, and every table
is truncated between tests so each test starts from a clean state. The test
database is always a separate database from development/production; destructive
setup never runs against the configured application database.
"""

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  (registers ORM models on Base.metadata)
from app.api.deps import get_db
from app.core.config import get_settings
from app.db.base import Base
from app.main import app as fastapi_app


def _test_database_url() -> str:
    """Resolve the test database URL.

    Prefers TEST_DATABASE_URL; otherwise derives `<db>_test` from the
    application's configured database URL so the two never collide.
    """
    override = os.getenv("TEST_DATABASE_URL")
    if override:
        return override

    app_url = make_url(get_settings().database_url)
    test_db_name = f"{app_url.database}_test"
    return app_url.set(database=test_db_name).render_as_string(hide_password=False)


TEST_DATABASE_URL = _test_database_url()


def _create_test_database() -> None:
    """(Re)create the test database using the `postgres` maintenance DB."""
    url = make_url(TEST_DATABASE_URL)
    db_name = url.database
    maintenance_url = url.set(database="postgres")

    engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        engine.dispose()


def _drop_test_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    db_name = url.database
    maintenance_url = url.set(database="postgres")

    engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            # Terminate lingering connections before dropping.
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def _engine() -> Generator:
    _create_test_database()
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()
        _drop_test_database()


@pytest.fixture()
def db_session(_engine) -> Generator[Session, None, None]:
    """A session bound to the test engine, with tables truncated afterward."""
    session_factory = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        # Clean every table so tests are isolated and order-independent.
        with _engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))


@pytest.fixture()
def client(_engine, db_session: Session) -> Generator[TestClient, None, None]:
    """A TestClient whose `get_db` dependency uses the test database."""

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(fastapi_app) as test_client:
            yield test_client
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)


def register_and_login(client: TestClient, email: str, password: str = "supersecret") -> dict:
    """Register a user, log in, and return an Authorization header dict."""
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def auth_headers(client: TestClient) -> dict:
    """Authorization header for a default authenticated user."""
    return register_and_login(client, "owner@example.com")
