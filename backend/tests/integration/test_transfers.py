"""Financial integration tests against a disposable PostgreSQL database."""

import asyncio
import os
import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, text as sql_text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import idempotency
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.modules.ledger.domain.services import calculate_account_balance
from app.modules.ledger.adapters.controllers import TransferRequest
from app.modules.ledger.infrastructure.models import (
    AccountModel, Base, LedgerEntryModel, TransactionModel, UserModel,
    TransactionStatus, TransactionType, UserModel,
)


@pytest_asyncio.fixture
async def ledger_db(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL must point to a disposable PostgreSQL database")
    schema = "test_transfers_" + uuid.uuid4().hex[:12]
    root_engine = create_async_engine(url, poolclass=NullPool)
    async with root_engine.begin() as connection:
        await connection.execute(sql_text(f'CREATE SCHEMA "{schema}"'))
    engine = root_engine.execution_options(schema_translate_map={None: schema})
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async def override_get_db():
            async with sessions() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        monkeypatch.setattr(idempotency, "get_session_factory", lambda: sessions)
        monkeypatch.setenv("DATABASE_URL", url)
        monkeypatch.setenv("JWT_SECRET_KEY", "t" * 64)
        monkeypatch.setenv("ADMIN_PASSWORD", "test-password-123")
        get_settings.cache_clear()
        yield sessions
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        async with root_engine.begin() as connection:
            await connection.execute(sql_text(f'DROP SCHEMA "{schema}" CASCADE'))
        await root_engine.dispose()


async def seed_accounts(sessions, amount=50000):
    async with sessions() as session:
        async with session.begin():
            sender = UserModel(email=f"sender-{uuid.uuid4()}@example.com", alias="sender",
                               password_hash="hash", full_name="Sender")
            recipient = UserModel(email=f"recipient-{uuid.uuid4()}@example.com", alias="recipient",
                                  password_hash="hash", full_name="Recipient")
            treasury = UserModel(email=f"treasury-{uuid.uuid4()}@example.com", alias="treasury",
                                 password_hash="hash", full_name="Treasury")
            session.add_all((sender, recipient, treasury))
            await session.flush()
            a = AccountModel(user_id=sender.id, account_number="S" + uuid.uuid4().hex[:19])
            b = AccountModel(user_id=recipient.id, account_number="R" + uuid.uuid4().hex[:19])
            system = AccountModel(user_id=treasury.id, account_number="T" + uuid.uuid4().hex[:19],
                                  type="SYSTEM_OMNIBUS")
            session.add_all((a, b, system))
            await session.flush()
            topup = TransactionModel(reference_id="TOPUP-" + uuid.uuid4().hex,
                                     type=TransactionType.TOPUP, status=TransactionStatus.SUCCESS,
                                     concept="Initial test funding")
            session.add(topup)
            await session.flush()
            session.add(LedgerEntryModel(transaction_id=topup.id, debit_account_id=system.id,
                                         credit_account_id=a.id, amount=amount))
            await session.flush()
    return sender, recipient, a, b


def headers(sender, key=None):
    token = create_access_token({"sub": str(sender.id), "email": sender.email,
                                 "alias": sender.alias, "role": "USER"})
    return {"Authorization": f"Bearer {token}",
            "X-Idempotency-Key": str(key or uuid.uuid4())}


def test_transfer_request_accepts_json_uuid_and_integer_amount():
    payload = TransferRequest.model_validate({
        "recipient_id": str(uuid.uuid4()), "amount": 1, "concept": "Prueba",
    })
    assert isinstance(payload.recipient_id, uuid.UUID)
    assert payload.amount == 1


@pytest.mark.asyncio
async def test_successful_transfer_changes_derived_balances_once(ledger_db):
    sender, recipient, a, b = await seed_accounts(ledger_db)
    payload = {"recipient_id": str(recipient.id), "amount": 20000, "concept": "Cena"}
    request_headers = headers(sender)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/api/v1/transfers/execute", json=payload, headers=request_headers)
        replay = await client.post("/api/v1/transfers/execute", json=payload, headers=request_headers)
        balance = await client.get("/api/v1/ledger/balance",
                                   headers={"Authorization": request_headers["Authorization"]})
    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    assert replay.headers["X-Cache"] == "HIT-IDEMPOTENCY"
    assert balance.status_code == 200 and balance.json()["balance"] == 30000
    async with ledger_db() as session:
        assert await calculate_account_balance(a.id, session) == 30000
        assert await calculate_account_balance(b.id, session) == 20000
        assert (await session.scalar(select(func.count()).select_from(LedgerEntryModel))) == 2


@pytest.mark.asyncio
async def test_insufficient_funds_creates_no_transaction_or_entry(ledger_db):
    sender, recipient, a, b = await seed_accounts(ledger_db)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/transfers/execute",
                                     json={"recipient_id": str(recipient.id), "amount": 50001,
                                           "concept": "Too much"}, headers=headers(sender))
    assert response.status_code == 400
    assert response.json()["code"] == "INSUFFICIENT_FUNDS"
    async with ledger_db() as session:
        assert await calculate_account_balance(a.id, session) == 50000
        assert await calculate_account_balance(b.id, session) == 0
        assert (await session.scalar(select(func.count()).select_from(TransactionModel))) == 1
        assert (await session.scalar(select(func.count()).select_from(LedgerEntryModel))) == 1


@pytest.mark.asyncio
async def test_parallel_transfers_cannot_overdraw_sender(ledger_db):
    sender, recipient, a, b = await seed_accounts(ledger_db)
    payload = {"recipient_id": str(recipient.id), "amount": 50000, "concept": "Race"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        responses = await asyncio.gather(*(
            client.post("/api/v1/transfers/execute", json=payload, headers=headers(sender))
            for _ in range(10)
        ))
    assert sorted(response.status_code for response in responses) == [201] + [400] * 9
    async with ledger_db() as session:
        assert await calculate_account_balance(a.id, session) == 0
        assert await calculate_account_balance(b.id, session) == 50000


@pytest.mark.asyncio
async def test_transfer_and_balance_routes_cover_identity_and_account_errors(ledger_db):
    sender, recipient, sender_account, _ = await seed_accounts(ledger_db)
    accountless = UserModel(email="accountless-transfer@example.com", alias="accountless_transfer",
                            password_hash="hash", full_name="Accountless")
    inactive = UserModel(email="inactive-transfer@example.com", alias="inactive_transfer",
                         password_hash="hash", full_name="Inactive", is_active=False)
    async with ledger_db() as session, session.begin():
        session.add_all((accountless, inactive))
    payload = {"recipient_id": str(recipient.id), "amount": 1, "concept": "Case"}
    token = headers(sender)["Authorization"]
    missing_user_token = create_access_token({"sub": str(uuid.uuid4()), "email": "missing@test.example",
                                              "alias": "missing_user", "role": "USER"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        self_transfer = await client.post("/api/v1/transfers/execute",
                                          json={**payload, "recipient_id": str(sender.id)},
                                          headers=headers(sender))
        absent_recipient = await client.post("/api/v1/transfers/execute",
                                             json={**payload, "recipient_id": str(uuid.uuid4())},
                                             headers=headers(sender))
        unauthenticated_transfer = await client.post("/api/v1/transfers/execute", json=payload,
                                                     headers={"X-Idempotency-Key": str(uuid.uuid4())})
        no_recipient_wallet = await client.post("/api/v1/transfers/execute",
                                                json={**payload, "recipient_id": str(accountless.id)},
                                                headers=headers(sender))
        inactive_token = create_access_token({"sub": str(inactive.id), "email": inactive.email,
                                              "alias": inactive.alias, "role": "USER"})
        accountless_token = create_access_token({"sub": str(accountless.id), "email": accountless.email,
                                                 "alias": accountless.alias, "role": "USER"})
        inactive_balance = await client.get("/api/v1/ledger/balance",
                                            headers={"Authorization": f"Bearer {inactive_token}"})
        no_wallet_balance = await client.get("/api/v1/ledger/balance",
                                            headers={"Authorization": f"Bearer {accountless_token}"})
        absent_user_balance = await client.get("/api/v1/ledger/balance",
                                               headers={"Authorization": f"Bearer {missing_user_token}"})
        no_auth_balance = await client.get("/api/v1/ledger/balance")
        good_balance = await client.get("/api/v1/ledger/balance", headers={"Authorization": token})
    assert self_transfer.status_code == 400
    assert absent_recipient.status_code == 404
    assert unauthenticated_transfer.status_code == 401
    assert no_recipient_wallet.status_code == 404
    assert inactive_balance.status_code == 401
    assert no_wallet_balance.status_code == 404
    assert absent_user_balance.status_code == 401
    assert no_auth_balance.status_code == 401
    assert good_balance.status_code == 200 and good_balance.json()["balance"] == 50000
    async with ledger_db() as session:
        assert await calculate_account_balance(sender_account.id, session) == 50000
