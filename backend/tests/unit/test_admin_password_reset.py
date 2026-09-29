"""The recovery command rotates only the configured administrator credential."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import admin_password_reset as reset
from app.modules.ledger.infrastructure.models import AuditLogModel, UserRole

pytestmark = pytest.mark.asyncio


async def test_reset_hashes_password_and_writes_audit_event(monkeypatch):
    admin = SimpleNamespace(id=uuid.uuid4(), role=UserRole.ADMIN, is_active=True,
                            password_hash="old-hash")
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=admin))
    monkeypatch.setattr(reset, "hash_password", lambda value: f"argon2:{value}")
    monkeypatch.setattr(reset, "verify_password", lambda value, hashed: hashed == f"argon2:{value}")

    await reset.rotate_admin_password(session, "admin@example.com", "A-new-strong-password!")

    assert admin.password_hash == "argon2:A-new-strong-password!"
    audit = session.add.call_args.args[0]
    assert isinstance(audit, AuditLogModel)
    assert audit.user_id == admin.id
    assert audit.action == "ADMIN_PASSWORD_RESET"
    assert audit.payload == {"method": "cli"}
    session.flush.assert_awaited_once()


@pytest.mark.parametrize("admin", [None,
    SimpleNamespace(id=uuid.uuid4(), role=UserRole.USER, is_active=True, password_hash="old"),
    SimpleNamespace(id=uuid.uuid4(), role=UserRole.ADMIN, is_active=False, password_hash="old"),
])
async def test_reset_rejects_missing_non_admin_or_inactive_accounts(admin):
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=admin))
    with pytest.raises(RuntimeError):
        await reset.rotate_admin_password(session, "admin@example.com", "A-new-strong-password!")
    session.add.assert_not_called()


async def test_reset_rejects_reusing_current_password(monkeypatch):
    admin = SimpleNamespace(id=uuid.uuid4(), role=UserRole.ADMIN, is_active=True,
                            password_hash="argon2:existing-password")
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=admin))
    monkeypatch.setattr(reset, "verify_password", lambda value, hashed: value == "existing-password")
    with pytest.raises(ValueError, match="diferente"):
        await reset.rotate_admin_password(session, "admin@example.com", "existing-password")
    session.add.assert_not_called()


@pytest.mark.parametrize("password", ["short", "x" * 129])
async def test_reset_requires_a_12_to_128_character_password(password):
    session = AsyncMock(spec=AsyncSession)
    with pytest.raises(ValueError):
        await reset.rotate_admin_password(session, "admin@example.com", password)
    session.execute.assert_not_called()
