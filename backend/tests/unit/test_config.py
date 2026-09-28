import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_validate_environment_and_secrets():
    data = {
        "DATABASE_URL": "postgresql+psycopg://user:password@localhost:5432/test",
        "JWT_SECRET_KEY": "x" * 64,
        "ADMIN_PASSWORD": "long-random-password",
    }
    settings = Settings(_env_file=None, **data)
    assert settings.DB_POOL_SIZE == 5
    assert settings.JWT_ALGORITHM == "HS256"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**data, "JWT_SECRET_KEY": "short"})
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**data, "DATABASE_URL": "sqlite:///test.db"})
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**data, "JWT_ALGORITHM": "none"})
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**data, "ENVIRONMENT": "production-ish"})


@pytest.mark.asyncio
async def test_session_factory_normalizes_postgres_url(monkeypatch):
    from app.core.config import get_settings
    from app.core.database import get_session_factory

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 64)
    monkeypatch.setenv("ADMIN_PASSWORD", "test-password-123")
    get_settings.cache_clear()
    get_session_factory.cache_clear()
    factory = get_session_factory()
    engine = factory.kw["bind"]
    try:
        assert engine.url.drivername == "postgresql+psycopg"
    finally:
        await engine.dispose()
        get_session_factory.cache_clear()
        get_settings.cache_clear()
