"""The global ledger has equal debit and credit totals, including issuance."""

import uuid

import pytest
from sqlalchemy import func, select

from app.modules.ledger.domain.services import calculate_account_balance
from app.modules.ledger.infrastructure.models import (
    AccountModel, AccountType, LedgerEntryModel, TransactionModel,
    TransactionStatus, TransactionType, UserModel,
)


@pytest.mark.asyncio
async def test_global_double_entry_sum_equals_zero(db_session, sessions):
    users = [UserModel(email=f"audit-{i}@test.example", alias=f"audit_{i}",
                       password_hash="test-hash", full_name=f"Audit {i}") for i in range(3)]
    db_session.add_all(users)
    await db_session.flush()
    accounts = [AccountModel(user_id=user.id, account_number=str(uuid.uuid4())[:20],
                             type=AccountType.SYSTEM_OMNIBUS if i == 0 else AccountType.USER_WALLET)
                for i, user in enumerate(users)]
    db_session.add_all(accounts)
    await db_session.flush()
    movements = (
        (TransactionType.TOPUP, accounts[0].id, accounts[1].id, 50000),
        (TransactionType.P2P_TRANSFER, accounts[1].id, accounts[2].id, 20000),
    )
    for kind, debit_id, credit_id, amount in movements:
        transaction = TransactionModel(reference_id=str(uuid.uuid4()), type=kind,
                                       status=TransactionStatus.SUCCESS, concept="Prueba contable")
        db_session.add(transaction)
        await db_session.flush()
        db_session.add(LedgerEntryModel(transaction_id=transaction.id,
                                        debit_account_id=debit_id,
                                        credit_account_id=credit_id, amount=amount))
    await db_session.commit()

    async with sessions() as verify:
        total_debits = await verify.scalar(select(func.coalesce(func.sum(LedgerEntryModel.amount), 0))
                                           .where(LedgerEntryModel.debit_account_id.is_not(None)))
        total_credits = await verify.scalar(select(func.coalesce(func.sum(LedgerEntryModel.amount), 0))
                                            .where(LedgerEntryModel.credit_account_id.is_not(None)))
        assert total_debits == total_credits == 70000
        assert total_credits - total_debits == 0
        balances = [await calculate_account_balance(account.id, verify) for account in accounts]
        assert balances == [-50000, 30000, 20000]
        assert sum(balances) == 0
