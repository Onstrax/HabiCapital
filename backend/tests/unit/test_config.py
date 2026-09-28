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
