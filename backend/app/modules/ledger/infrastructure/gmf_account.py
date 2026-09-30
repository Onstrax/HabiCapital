"""Idempotent provisioning of the single system collector; it has no login identity."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.modules.ledger.infrastructure.models import AccountModel, AccountType
from app.shared.exceptions import TaxAccountConfigurationException

async def ensure_gmf_account(session: AsyncSession) -> AccountModel:
    account_id = get_settings().SYSTEM_TAX_GMF_ACCOUNT_ID
    existing = (await session.execute(select(AccountModel).where(
        AccountModel.type == AccountType.SYSTEM_TAX_GMF))).scalars().all()
    if existing:
        if len(existing) != 1 or existing[0].id != account_id or existing[0].user_id is not None:
            raise TaxAccountConfigurationException("La cuenta GMF requiere conciliación; no cambies su UUID")
        return existing[0]
    if await session.get(AccountModel, account_id) is not None:
        raise TaxAccountConfigurationException("El UUID GMF ya pertenece a otra cuenta")
    account = AccountModel(id=account_id, user_id=None, account_number="SYSTEM-TAX-GMF",
                           type=AccountType.SYSTEM_TAX_GMF)
    session.add(account)
    await session.flush()
    return account
