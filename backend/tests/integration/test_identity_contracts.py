import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import hash_password
from app.main import app
from app.modules.identity.adapters.controllers import get_identity_repository
from app.modules.identity.use_cases.identity import Identity


@pytest.fixture(autouse=True)
def configured_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", "s" * 64)
    monkeypatch.setenv("ADMIN_PASSWORD", "test-password-123")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_register_login_and_exact_lookup_contracts():
    user_id = uuid.uuid4()
    existing = Identity(id=user_id, email="juan@example.com", alias="juan_1",
                        full_name="Juan Esteban Gómez", role="USER", is_active=True,
                        password_hash=hash_password("Password123!"),
                        created_at=datetime.now(timezone.utc))
    repo = AsyncMock()
    repo.register.return_value = existing
    repo.find_by_email.return_value = existing
    repo.find_by_alias.return_value = existing
    app.dependency_overrides[get_identity_repository] = lambda: repo
    try:
        with TestClient(app) as client:
            registered = client.post("/api/v1/auth/register", json={
                "email": "juan@example.com", "alias": "JUAN_1", "password": "Password123!",
                "full_name": "Juan Esteban Gómez",
            })
            assert registered.status_code == 201
            assert registered.json()["alias"] == "juan_1"
            assert "password_hash" not in registered.json()
            logged_in = client.post("/api/v1/auth/login", json={
                "email": "juan@example.com", "password": "Password123!",
            })
            assert logged_in.status_code == 200
            assert logged_in.json()["expires_in"] == 900
            token = logged_in.json()["access_token"]
            looked_up = client.post("/api/v1/transfers/lookup", json={"recipient_alias": "juan_1"},
                                    headers={"Authorization": f"Bearer {token}"})
            assert looked_up.status_code == 200
            assert looked_up.json() == {"recipient_id": str(user_id), "recipient_alias": "juan_1",
                                        "masked_name": "J*** E****** G****"}
            repo.find_by_alias.assert_awaited_with("juan_1")
    finally:
        app.dependency_overrides.clear()


def test_lookup_requires_token_and_extra_fields_are_rejected():
    with TestClient(app) as client:
        assert client.post("/api/v1/transfers/lookup", json={"recipient_alias": "juan_1"}).status_code == 401
        invalid = client.post("/api/v1/auth/register", json={
            "email": "juan@example.com", "alias": "juan_1", "password": "Password123!",
            "full_name": "Juan Esteban Gómez", "role": "ADMIN",
        })
        assert invalid.status_code == 422
