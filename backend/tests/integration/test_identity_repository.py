"""Exercise the real SQL identity repository against the isolated test schema."""

import uuid

import pytest
from sqlalchemy import select

from app.modules.identity.infrastructure.repository import SqlIdentityRepository
from app.modules.ledger.infrastructure.models import AccountModel


@pytest.mark.asyncio
async def test_sql_identity_repository_registers_wallet_and_supports_lookups(db_session):
    repo = SqlIdentityRepository(db_session)
    marker = uuid.uuid4().hex[:10]
    user = await repo.register(f"{marker}@example.test", f"u{marker}", "argon-hash", "Test User")
    assert user.alias == f"u{marker}"
    assert (await repo.find_by_email(user.email)).id == user.id
    assert (await repo.find_by_alias(user.alias)).id == user.id
    assert (await repo.find_by_id(user.id)).id == user.id
    assert await repo.find_by_email("absent@example.test") is None
    assert await repo.find_by_alias("absent_user") is None
    assert await repo.find_by_id(uuid.uuid4()) is None
    account = await db_session.scalar(select(AccountModel).where(AccountModel.user_id == user.id))
    assert account is not None
