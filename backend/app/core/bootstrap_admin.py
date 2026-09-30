"""Run explicitly after migrations: python -m app.core.bootstrap_admin."""

import asyncio
import uuid

from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.field_encryption import blind_index
from app.core.database import get_session_factory
from app.core.security import hash_password
from app.modules.ledger.infrastructure.gmf_account import ensure_gmf_account
from app.modules.ledger.infrastructure.models import (
    AccountModel, AccountType, UserModel, UserRole,
)
from app.shared.utils.security_utils import sanitize_alias


async def bootstrap_admin() -> None:
    settings = get_settings()
    alias = sanitize_alias(settings.ADMIN_ALIAS)
    async with get_session_factory()() as session, session.begin():
        # Serialize repeated invocations so there is exactly one omnibus account.
        await session.execute(text("SELECT pg_advisory_xact_lock(214897301)"))
        await ensure_gmf_account(session)
        existing_omnibus = (await session.execute(select(AccountModel).where(
            AccountModel.type == AccountType.SYSTEM_OMNIBUS))).scalars().all()
        admin = (await session.execute(select(UserModel).where(
            UserModel.email_blind_index == blind_index(settings.ADMIN_EMAIL)))).scalar_one_or_none()
        if admin is None:
            if existing_omnibus:
                raise RuntimeError("La cuenta ómnibus ya existe; requiere conciliación manual")
            admin = UserModel(email=settings.ADMIN_EMAIL, alias=alias,
                              password_hash=hash_password(settings.ADMIN_PASSWORD),
                              full_name="Administrador HabiCapital", role=UserRole.ADMIN)
            session.add(admin)
            await session.flush()
        elif admin.role != UserRole.ADMIN or not admin.is_active or admin.alias != alias:
            raise RuntimeError("El usuario administrador configurado presenta un conflicto")
        if existing_omnibus:
            if len(existing_omnibus) != 1 or existing_omnibus[0].user_id != admin.id:
                raise RuntimeError("La cuenta ómnibus requiere conciliación manual")
        else:
            existing_account = (await session.execute(select(AccountModel).where(
                AccountModel.user_id == admin.id))).scalar_one_or_none()
            if existing_account is not None:
                raise RuntimeError("El administrador ya tiene otra cuenta; requiere conciliación manual")
            session.add(AccountModel(user_id=admin.id,
                                     account_number="SYS" + uuid.uuid4().hex[:17],
                                     type=AccountType.SYSTEM_OMNIBUS))


if __name__ == "__main__":
    asyncio.run(bootstrap_admin())
