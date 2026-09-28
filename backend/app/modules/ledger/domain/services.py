"""Exact balance query derived exclusively from immutable ledger entries."""

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledger.infrastructure.models import LedgerEntryModel


async def calculate_account_balance(account_id: uuid.UUID, session: AsyncSession) -> int:
    statement = select(
        func.coalesce(func.sum(case(
            (LedgerEntryModel.credit_account_id == account_id, LedgerEntryModel.amount),
            else_=0,
        )), 0)
        - func.coalesce(func.sum(case(
            (LedgerEntryModel.debit_account_id == account_id, LedgerEntryModel.amount),
            else_=0,
        )), 0)
    )
    return int((await session.execute(statement)).scalar_one())
