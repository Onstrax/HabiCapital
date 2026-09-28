"""A sender can spend a 50,000 COP balance exactly once under simultaneous load."""

import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.modules.ledger.domain.services import calculate_account_balance
from app.modules.ledger.infrastructure.models import (
    AccountModel, AccountType, LedgerEntryModel, TransactionModel,
    TransactionStatus, TransactionType, UserModel,
)


@pytest.mark.asyncio
async def test_concurrent_transfers_prevent_overdraft(async_client, db_session, sessions):
    user_a = UserModel(email="usera@test.example", alias="user_a",
                       password_hash="test-hash", full_name="User A")
    user_b = UserModel(email="userb@test.example", alias="user_b",
                       password_hash="test-hash", full_name="User B")
    system = UserModel(email="system@test.example", alias="system_account",
                       password_hash="test-hash", full_name="System")
    db_session.add_all((user_a, user_b, system))
    await db_session.flush()
    account_a = AccountModel(user_id=user_a.id, account_number="A" + uuid.uuid4().hex[:19])
    account_b = AccountModel(user_id=user_b.id, account_number="B" + uuid.uuid4().hex[:19])
    omnibus = AccountModel(user_id=system.id, account_number="O" + uuid.uuid4().hex[:19],
                           type=AccountType.SYSTEM_OMNIBUS)
    db_session.add_all((account_a, account_b, omnibus))
    await db_session.flush()
    funding = TransactionModel(reference_id="TOPUP-" + uuid.uuid4().hex,
                               type=TransactionType.TOPUP, status=TransactionStatus.SUCCESS,
                               concept="Saldo inicial de prueba")
    db_session.add(funding)
    await db_session.flush()
    db_session.add(LedgerEntryModel(transaction_id=funding.id,
                                    debit_account_id=omnibus.id,
                                    credit_account_id=account_a.id, amount=50000))
    await db_session.commit()  # Make the seed visible to every independent request.

    token = create_access_token({"sub": str(user_a.id), "email": user_a.email,
                                 "alias": user_a.alias, "role": "USER"})
    payload = {"recipient_id": str(user_b.id), "amount": 50000,
               "concept": "Transferencia concurrente"}

    async def send_transfer():
        return await async_client.post("/api/v1/transfers/execute", json=payload,
                                       headers={"Authorization": f"Bearer {token}",
                                                "X-Idempotency-Key": str(uuid.uuid4())})

    responses = await asyncio.gather(*(send_transfer() for _ in range(10)))
    assert sum(response.status_code == 201 for response in responses) == 1
    assert sum(response.status_code == 400 for response in responses) == 9
    assert all(response.json().get("code") == "INSUFFICIENT_FUNDS"
               for response in responses if response.status_code == 400)

    async with sessions() as verify:
        assert await calculate_account_balance(account_a.id, verify) == 0
        assert await calculate_account_balance(account_b.id, verify) == 50000
        assert await verify.scalar(select(func.count()).select_from(LedgerEntryModel)) == 2
        assert await verify.scalar(select(func.count()).select_from(TransactionModel).where(
            TransactionModel.type == TransactionType.P2P_TRANSFER)) == 1
