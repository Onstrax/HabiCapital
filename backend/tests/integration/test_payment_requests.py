"""End-to-end charge transitions and administrator funding on PostgreSQL."""

import asyncio
import os
import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import idempotency
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.core import bootstrap_admin as bootstrap_module
from app.main import app
from app.modules.ledger.domain.services import calculate_account_balance
from app.modules.ledger.infrastructure.models import (
    AccountModel, AccountType, AuditLogModel, Base, LedgerEntryModel,
    PaymentRequestModel, PaymentRequestStatus, TransactionModel, TransactionType,
    UserModel, UserRole,
)


def test_charge_and_topup_routes_are_registered():
    paths = set(app.openapi()["paths"])
    assert {"/api/v1/charges", "/api/v1/charges/{charge_id}/pay",
            "/api/v1/charges/{charge_id}/reject", "/api/v1/charges/{charge_id}/cancel",
            "/api/v1/admin/topup"} <= paths


@pytest_asyncio.fixture
async def payments_db(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL must point to a disposable PostgreSQL database")
    schema = "test_charges_" + uuid.uuid4().hex[:12]
    root_engine = create_async_engine(url, poolclass=NullPool)
    async with root_engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = root_engine.execution_options(schema_translate_map={None: schema})
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async def override_db():
            async with sessions() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        monkeypatch.setattr(idempotency, "get_session_factory", lambda: sessions)
        monkeypatch.setenv("DATABASE_URL", url)
        monkeypatch.setenv("JWT_SECRET_KEY", "t" * 64)
        monkeypatch.setenv("ADMIN_PASSWORD", "test-password-123")
        get_settings.cache_clear()
        yield sessions
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        async with root_engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await root_engine.dispose()


async def seed(sessions):
    async with sessions() as session, session.begin():
        requester = UserModel(email="requester@example.com", alias="requester",
                              password_hash="hash", full_name="Requester")
        payer = UserModel(email="payer@example.com", alias="payer",
                          password_hash="hash", full_name="Payer")
        admin = UserModel(email="admin@example.com", alias="adminuser",
                          password_hash="hash", full_name="Admin", role=UserRole.ADMIN)
        session.add_all((requester, payer, admin))
        await session.flush()
        requester_acc = AccountModel(user_id=requester.id, account_number="A" + uuid.uuid4().hex[:19])
        payer_acc = AccountModel(user_id=payer.id, account_number="B" + uuid.uuid4().hex[:19])
        omnibus = AccountModel(user_id=admin.id, account_number="O" + uuid.uuid4().hex[:19],
                               type=AccountType.SYSTEM_OMNIBUS)
        session.add_all((requester_acc, payer_acc, omnibus))
        await session.flush()
    return requester, payer, admin, requester_acc, payer_acc, omnibus


@pytest.mark.asyncio
async def test_admin_bootstrap_creates_one_admin_and_one_omnibus(payments_db, monkeypatch):
    monkeypatch.setattr(bootstrap_module, "get_session_factory", lambda: payments_db)
    await bootstrap_module.bootstrap_admin()
    await bootstrap_module.bootstrap_admin()
    async with payments_db() as session:
        assert await session.scalar(select(func.count()).select_from(UserModel).where(
            UserModel.role == UserRole.ADMIN)) == 1
        assert await session.scalar(select(func.count()).select_from(AccountModel).where(
            AccountModel.type == AccountType.SYSTEM_OMNIBUS)) == 1


def auth(user, *, key=False, claim_role=None):
    role = claim_role or user.role.value
    token = create_access_token({"sub": str(user.id), "email": user.email,
                                 "alias": user.alias, "role": role})
    result = {"Authorization": "Bearer " + token}
    if key:
        result["X-Idempotency-Key"] = str(uuid.uuid4())
    return result


@pytest.mark.asyncio
async def test_admin_topup_and_successful_charge_payment(payments_db):
    requester, payer, admin, requester_acc, payer_acc, omnibus = await seed(payments_db)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        forbidden = await client.post("/api/v1/admin/topup", headers=auth(payer, key=True),
                                      json={"target_user_alias": "payer", "amount": 30000,
                                            "concept": "Recarga"})
        forged = await client.post("/api/v1/admin/topup", headers=auth(payer, key=True, claim_role="ADMIN"),
                                   json={"target_user_alias": "payer", "amount": 30000,
                                         "concept": "Recarga"})
        topup_headers = auth(admin, key=True)
        topup = await client.post("/api/v1/admin/topup", headers=topup_headers,
                                  json={"target_user_alias": "payer", "amount": 30000,
                                        "concept": "Recarga"})
        replay_topup = await client.post("/api/v1/admin/topup", headers=topup_headers,
                                         json={"target_user_alias": "payer", "amount": 30000,
                                               "concept": "Recarga"})
        charge = await client.post("/api/v1/charges", headers=auth(requester),
                                   json={"payer_alias": "payer", "amount": 25000,
                                         "concept": "Cine"})
        charge_id = charge.json().get("id")
        pay_headers = auth(payer, key=True)
        paid = await client.post(f"/api/v1/charges/{charge_id}/pay", headers=pay_headers)
        replay_paid = await client.post(f"/api/v1/charges/{charge_id}/pay", headers=pay_headers)
        terminal = await client.post(f"/api/v1/charges/{charge_id}/reject", headers=auth(payer))
    assert forbidden.status_code == forged.status_code == 403
    assert topup.status_code == replay_topup.status_code == 200
    assert replay_topup.headers["X-Cache"] == "HIT-IDEMPOTENCY"
    assert topup.json()["new_target_balance"] == 30000
    assert charge.status_code == 201 and charge.json()["status"] == "PENDING"
    assert paid.status_code == replay_paid.status_code == 200
    assert replay_paid.headers["X-Cache"] == "HIT-IDEMPOTENCY"
    assert paid.json()["status"] == "COMPLETED" and paid.json() == replay_paid.json()
    assert terminal.status_code == 409
    async with payments_db() as session:
        assert await calculate_account_balance(payer_acc.id, session) == 5000
        assert await calculate_account_balance(requester_acc.id, session) == 25000
        assert await calculate_account_balance(omnibus.id, session) == -30000
        assert (await session.get(PaymentRequestModel, uuid.UUID(charge_id))).status == PaymentRequestStatus.COMPLETED
        assert await session.scalar(select(func.count()).select_from(LedgerEntryModel)) == 2
        assert await session.scalar(select(func.count()).select_from(TransactionModel).where(
            TransactionModel.type == TransactionType.PAYMENT_REQUEST_PAYMENT)) == 1


@pytest.mark.asyncio
async def test_insufficient_funds_keeps_charge_pending_and_audits_failure(payments_db):
    requester, payer, _, requester_acc, payer_acc, _ = await seed(payments_db)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        charge = await client.post("/api/v1/charges", headers=auth(requester),
                                   json={"payer_alias": "payer", "amount": 25000,
                                         "concept": "Cine"})
        charge_id = charge.json().get("id")
        denied = await client.post(f"/api/v1/charges/{charge_id}/pay", headers=auth(requester, key=True))
        response = await client.post(f"/api/v1/charges/{charge_id}/pay", headers=auth(payer, key=True))
    assert charge.status_code == 201 and denied.status_code == 403
    assert response.status_code == 400
    assert response.json()["code"] == "INSUFFICIENT_FUNDS_FOR_PAYMENT_REQUEST"
    assert response.json()["details"] == {"current_balance": 0, "required_amount": 25000,
                                           "charge_status": "PENDING"}
    async with payments_db() as session:
        assert (await session.get(PaymentRequestModel, uuid.UUID(charge_id))).status == PaymentRequestStatus.PENDING
        assert await calculate_account_balance(payer_acc.id, session) == 0
        assert await calculate_account_balance(requester_acc.id, session) == 0
        assert await session.scalar(select(func.count()).select_from(TransactionModel)) == 0
        assert await session.scalar(select(func.count()).select_from(LedgerEntryModel)) == 0
        assert await session.scalar(select(func.count()).select_from(AuditLogModel).where(
            AuditLogModel.action == "PAYMENT_REQUEST_INSUFFICIENT_FUNDS")) == 1


@pytest.mark.asyncio
async def test_reject_cancel_authorization_and_terminal_states(payments_db):
    requester, payer, _, _, _, _ = await seed(payments_db)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = (await client.post("/api/v1/charges", headers=auth(requester),
                                  json={"payer_alias": "payer", "amount": 1, "concept": "Uno"})).json()["id"]
        second = (await client.post("/api/v1/charges", headers=auth(requester),
                                   json={"payer_alias": "payer", "amount": 1, "concept": "Dos"})).json()["id"]
        denied = await client.post(f"/api/v1/charges/{first}/reject", headers=auth(requester))
        reject = await client.post(f"/api/v1/charges/{first}/reject", headers=auth(payer))
        denied_cancel = await client.post(f"/api/v1/charges/{second}/cancel", headers=auth(payer))
        cancel = await client.post(f"/api/v1/charges/{second}/cancel", headers=auth(requester))
        terminal = await client.post(f"/api/v1/charges/{first}/pay", headers=auth(payer, key=True))
    assert denied.status_code == denied_cancel.status_code == 403
    assert reject.status_code == cancel.status_code == 200
    assert reject.json()["status"] == "REJECTED" and cancel.json()["status"] == "CANCELLED"
    assert terminal.status_code == 409


@pytest.mark.asyncio
async def test_concurrent_payment_creates_exactly_one_ledger_entry(payments_db):
    requester, payer, admin, _, payer_acc, _ = await seed(payments_db)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/admin/topup", headers=auth(admin, key=True),
                          json={"target_user_alias": "payer", "amount": 50000, "concept": "Recarga"})
        charge_id = (await client.post("/api/v1/charges", headers=auth(requester),
                                       json={"payer_alias": "payer", "amount": 50000,
                                             "concept": "Simultáneo"})).json()["id"]
        responses = await asyncio.gather(*(
            client.post(f"/api/v1/charges/{charge_id}/pay", headers=auth(payer, key=True))
            for _ in range(2)
        ))
    assert sorted(response.status_code for response in responses) == [200, 409]
    async with payments_db() as session:
        assert await calculate_account_balance(payer_acc.id, session) == 0
        assert await session.scalar(select(func.count()).select_from(LedgerEntryModel)) == 2
