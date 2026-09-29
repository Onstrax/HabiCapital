"""Public API contract for administrator audit consultation."""

from app.main import app


def test_read_limit_rejects_61st_request_for_one_session(monkeypatch):
    import uuid
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock
    from fastapi.testclient import TestClient
    from app.core.config import get_settings
    from app.core.security import create_access_token
    from app.modules.identity.adapters.controllers import get_identity_repository
    from app.modules.identity.use_cases.identity import Identity

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", "s" * 64)
    monkeypatch.setenv("ADMIN_PASSWORD", "test-password-123")
    get_settings.cache_clear()
    actor_id = uuid.uuid4()
    repo = AsyncMock()
    repo.find_by_id.return_value = Identity(
        id=actor_id, email="rate@example.test", alias="rateactor", full_name="Rate Actor",
        role="USER", is_active=True, password_hash="hash", created_at=datetime.now(timezone.utc),
    )
    app.dependency_overrides[get_identity_repository] = lambda: repo
    try:
        token = create_access_token({"sub": str(actor_id)})
        with TestClient(app) as client:
            for _ in range(60):
                assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
            last = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert last.status_code == 429
            assert last.json()["code"] == "RATE_LIMIT_EXCEEDED"
    finally:
        app.dependency_overrides.pop(get_identity_repository, None)
        get_settings.cache_clear()


def test_admin_audit_read_is_registered_and_requires_bearer_auth():
    contract = app.openapi()["paths"]["/api/v1/admin/audit"]["get"]
    assert contract["security"] == [{"HTTPBearer": []}]
    assert contract["responses"]["200"]["content"]["application/json"]
