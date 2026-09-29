"""PostgreSQL persistence for identity and atomic wallet creation."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.field_encryption import blind_index

from app.modules.identity.use_cases.identity import Identity
from app.modules.ledger.infrastructure.models import AccountModel, AccountType, UserModel


def identity_from_row(row: UserModel) -> Identity:
    return Identity(id=row.id, email=row.email, alias=row.alias, full_name=row.full_name,
                    role=row.role.value, is_active=row.is_active,
                    password_hash=row.password_hash, created_at=row.created_at)


class SqlIdentityRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def register(self, email: str, alias: str, password_hash: str, full_name: str) -> Identity:
        async with self.session.begin():
            user = UserModel(email=email, alias=alias, password_hash=password_hash,
                             full_name=full_name)
            self.session.add(user)
            await self.session.flush()
            self.session.add(AccountModel(user_id=user.id,
                                          account_number="ACC-" + uuid.uuid4().hex[:16].upper(),
                                          type=AccountType.USER_WALLET))
            await self.session.flush()
            result = identity_from_row(user)
        return result

    async def find_by_email(self, email: str) -> Identity | None:
        row = (await self.session.execute(select(UserModel).where(
            UserModel.email_blind_index == blind_index(email)))).scalar_one_or_none()
        return identity_from_row(row) if row else None

    async def find_by_alias(self, alias: str) -> Identity | None:
        row = (await self.session.execute(select(UserModel).where(
            UserModel.alias_blind_index == blind_index(alias, "users.alias")))).scalar_one_or_none()
        return identity_from_row(row) if row else None

    async def find_by_id(self, user_id: uuid.UUID) -> Identity | None:
        row = await self.session.get(UserModel, user_id)
        return identity_from_row(row) if row else None
