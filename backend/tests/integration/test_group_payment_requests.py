"""Group creation is atomic; the owner sees each recipient's current state."""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.modules.ledger.infrastructure.models import (
    AccountModel, AuditLogModel, LedgerEntryModel, PaymentRequestModel,
    TransactionModel, TransactionStatus, TransactionType, UserModel, UserRole,
)


async def seed_group(sessions):
    async with sessions() as session, session.begin():
        creator, payer_a, payer_b, stranger, admin = [
            UserModel(email=f"{name}-{uuid.uuid4()}@example.test", alias=name,
                      full_name=name.title(), password_hash="hash", role=role)
            for name, role in (("creator", UserRole.USER), ("payer_a", UserRole.USER),
                               ("payer_b", UserRole.USER), ("stranger", UserRole.USER),
                               ("admin", UserRole.ADMIN))
        ]
        session.add_all((creator, payer_a, payer_b, stranger, admin))
        await session.flush()
        accounts = {}
        for user in (creator, payer_a, payer_b, stranger, admin):
            from app.modules.ledger.infrastructure.models import AccountType
            account = AccountModel(user_id=user.id, account_number="A" + uuid.uuid4().hex[:19],
                                   type=AccountType.SYSTEM_OMNIBUS if user is admin else AccountType.USER_WALLET)
            session.add(account)
            accounts[user.alias] = account
        await session.flush()
        return {user.alias: user.id for user in (creator, payer_a, payer_b, stranger, admin)}, {
            name: account.id for name, account in accounts.items()
        }


def headers(user_id, *, key=False):
    value = {"Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"}
    if key:
        value["X-Idempotency-Key"] = str(uuid.uuid4())
    return value


def group_payload():
    return {"total_amount": 100_000, "concept": "Almuerzo equipo", "recipients": [
        {"recipient_alias": "payer_a", "percentage": 50.0, "is_locked": True},
        {"recipient_alias": "payer_b", "percentage": 50.0, "is_locked": False},
    ]}


@pytest.mark.asyncio
async def test_group_creates_n_atomic_rows_with_same_group_id(sessions, async_client):
    users, accounts = await seed_group(sessions)
    created = await async_client.post("/api/v1/charges/group", json=group_payload(),
                                      headers=headers(users["creator"], key=True))
    assert created.status_code == 201, created.text
    assert created.json()["group_id"]
    assert len(created.json()["items"]) == 2
    assert sum(row["amount"] for row in created.json()["items"]) == 100_000
    async with sessions() as session:
        rows = (await session.execute(select(PaymentRequestModel).where(
            PaymentRequestModel.group_id == uuid.UUID(created.json()["group_id"])))).scalars().all()
        assert len(rows) == 2
        assert {row.requester_account_id for row in rows} == {accounts["creator"]}
        assert {row.payer_account_id for row in rows} == {accounts["payer_a"], accounts["payer_b"]}
        assert sum(row.amount for row in rows) == 100_000
        assert {str(row.percentage) for row in rows} == {"50.00"}


@pytest.mark.asyncio
async def test_created_charges_are_visible_only_to_owner_with_current_status(sessions, async_client):
    users, _ = await seed_group(sessions)
    created = await async_client.post("/api/v1/charges/group", json=group_payload(),
                                      headers=headers(users["creator"], key=True))
    assert created.status_code == 201
    mine = await async_client.get("/api/v1/charges/created", headers=headers(users["creator"]))
    assert mine.status_code == 200
    assert len(mine.json()["items"]) == 2
    assert all(row["status"] == "PENDING" and row["updated_at"] and row["masked_name"]
               and row["percentage"] == 50 for row in mine.json()["items"])
    assert all("full_name" not in row for row in mine.json()["items"])
    other = await async_client.get("/api/v1/charges/created", headers=headers(users["stranger"]))
    assert other.status_code == 200 and other.json()["items"] == []
    denied = await async_client.post(f"/api/v1/charges/{created.json()['items'][0]['id']}/cancel",
                                     headers=headers(users["stranger"], key=True))
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_one_payer_completes_other_stays_pending_and_owner_sees_it(sessions, async_client):
    users, accounts = await seed_group(sessions)
    async with sessions() as session, session.begin():
        funding = TransactionModel(reference_id="TOPUP-" + uuid.uuid4().hex,
                                   type=TransactionType.TOPUP, status=TransactionStatus.SUCCESS,
                                   concept="Saldo de prueba")
        session.add(funding)
        await session.flush()
        session.add(LedgerEntryModel(transaction_id=funding.id, debit_account_id=accounts["admin"],
                                    credit_account_id=accounts["payer_a"], amount=50_200))
    created = await async_client.post("/api/v1/charges/group", json=group_payload(),
                                      headers=headers(users["creator"], key=True))
    assert created.status_code == 201
    ids = {row["payer_alias"]: row["id"] for row in created.json()["items"]}
    paid = await async_client.post(f"/api/v1/charges/{ids['payer_a']}/pay",
                                   headers=headers(users["payer_a"], key=True))
    assert paid.status_code == 200
    mine = await async_client.get("/api/v1/charges/created", headers=headers(users["creator"]))
    assert {row["payer_alias"]: row["status"] for row in mine.json()["items"]} == {
        "payer_a": "COMPLETED", "payer_b": "PENDING",
    }
    pending = await async_client.get("/api/v1/charges/pending", headers=headers(users["payer_b"]))
    assert pending.status_code == 200
    assert [row["id"] for row in pending.json()["items"]] == [ids["payer_b"]]
    cancelled = await async_client.post(f"/api/v1/charges/{ids['payer_b']}/cancel",
                                        headers=headers(users["creator"], key=True))
    assert cancelled.status_code == 200
    mine_after = await async_client.get("/api/v1/charges/created", headers=headers(users["creator"]))
    assert {row["payer_alias"]: row["status"] for row in mine_after.json()["items"]} == {
        "payer_a": "COMPLETED", "payer_b": "CANCELLED",
    }


@pytest.mark.asyncio
async def test_group_rejects_duplicate_alias_and_too_small_total_without_partial_rows(sessions, async_client):
    users, _ = await seed_group(sessions)
    missing_key = await async_client.post("/api/v1/charges/group", json=group_payload(),
                                          headers=headers(users["creator"]))
    assert missing_key.status_code == 400 and missing_key.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    payload = group_payload()
    payload["recipients"][1]["recipient_alias"] = "payer_a"
    conflict = await async_client.post("/api/v1/charges/group", json=payload,
                                       headers=headers(users["creator"], key=True))
    assert conflict.status_code == 422
    payload = group_payload()
    payload["total_amount"] = 1
    zero = await async_client.post("/api/v1/charges/group", json=payload,
                                   headers=headers(users["creator"], key=True))
    assert zero.status_code == 422
    async with sessions() as session:
        assert (await session.execute(select(PaymentRequestModel))).scalars().all() == []


@pytest.mark.asyncio
async def test_owner_can_track_rejected_and_cancelled_items_without_exposing_to_others(sessions, async_client):
    users, _ = await seed_group(sessions)
    created = await async_client.post("/api/v1/charges/group", json=group_payload(),
                                      headers=headers(users["creator"], key=True))
    assert created.status_code == 201
    ids = {item["payer_alias"]: item["id"] for item in created.json()["items"]}
    rejected = await async_client.post(f"/api/v1/charges/{ids['payer_a']}/reject",
                                       headers=headers(users["payer_a"], key=True))
    assert rejected.status_code == 200
    cancelled = await async_client.post(f"/api/v1/charges/{ids['payer_b']}/cancel",
                                        headers=headers(users["creator"], key=True))
    assert cancelled.status_code == 200
    mine = await async_client.get("/api/v1/charges/created", headers=headers(users["creator"]))
    assert {row["payer_alias"]: row["status"] for row in mine.json()["items"]} == {
        "payer_a": "REJECTED", "payer_b": "CANCELLED",
    }
    outsider = await async_client.get("/api/v1/charges/created", headers=headers(users["stranger"]))
    assert outsider.status_code == 200 and outsider.json()["items"] == []
