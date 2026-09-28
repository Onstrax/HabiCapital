"""Isolated PostgreSQL fixtures with independent sessions for concurrent HTTP requests."""

import os
import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import idempotency
from app.core.config import get_settings
from app.core.database import get_db
from app.main import app
from app.modules.ledger.infrastructure.models import Base


@pytest_asyncio.fixture
async def test_engine(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database")
    schema = "test_integrity_" + uuid.uuid4().hex[:12]
    root_engine = create_async_engine(url, poolclass=NullPool)
    async with root_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = root_engine.execution_options(schema_translate_map={None: schema})
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        monkeypatch.setenv("DATABASE_URL", url)
        monkeypatch.setenv("JWT_SECRET_KEY", "t" * 64)
        monkeypatch.setenv("ADMIN_PASSWORD", "test-password-123")
        get_settings.cache_clear()
        yield engine
    finally:
        get_settings.cache_clear()
        async with root_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await root_engine.dispose()


@pytest.fixture
def sessions(test_engine):
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(sessions):
    async with sessions() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def async_client(sessions, monkeypatch):
    async def override_get_db():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(idempotency, "get_session_factory", lambda: sessions)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://testserver") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
