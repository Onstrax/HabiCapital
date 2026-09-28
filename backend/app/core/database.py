"""Async PostgreSQL sessions; each mutating use case owns its transaction."""

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    settings = get_settings()
    url = str(settings.DATABASE_URL)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_async_engine(url, pool_pre_ping=True,
                                 pool_size=settings.DB_POOL_SIZE,
                                 max_overflow=settings.DB_MAX_OVERFLOW)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with get_session_factory()() as session:
        yield session
