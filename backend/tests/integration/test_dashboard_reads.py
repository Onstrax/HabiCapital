"""Read views must stay scoped to the authenticated wallet."""

import pytest

from app.modules.ledger.infrastructure.models import PaymentRequestModel
from tests.integration.test_transfers import ledger_db, seed_accounts, headers


@pytest.mark.asyncio
async def test_ledger_history_is_signed_and_user_scoped(ledger_db):
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    sender, recipient, _, _ = await seed_accounts(ledger_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        own = await client.get("/api/v1/ledger/movements", headers=headers(sender))
        other = await client.get("/api/v1/ledger/movements", headers=headers(recipient))
        anonymous = await client.get("/api/v1/ledger/movements")
    assert own.status_code == other.status_code == 200
    assert anonymous.status_code == 401
    assert len(own.json()["items"]) == 1
    assert own.json()["items"][0]["direction"] == "IN"
    assert own.json()["items"][0]["amount"] == 50000
    assert other.json()["items"] == []


@pytest.mark.asyncio
async def test_pending_charges_are_visible_only_to_payer(ledger_db):
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    sender, recipient, a, b = await seed_accounts(ledger_db)
    async with ledger_db() as session, session.begin():
        session.add(PaymentRequestModel(requester_account_id=a.id, payer_account_id=b.id,
                                        amount=1234, concept="Almuerzo"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payer = await client.get("/api/v1/charges?status=PENDING", headers=headers(recipient))
        requester = await client.get("/api/v1/charges?status=PENDING", headers=headers(sender))
        anonymous = await client.get("/api/v1/charges?status=PENDING")
    assert payer.status_code == requester.status_code == 200
    assert anonymous.status_code == 401
    assert len(payer.json()["items"]) == 1
    assert payer.json()["items"][0]["requester_alias"] == "sender"
    assert payer.json()["items"][0]["amount"] == 1234
    assert requester.json()["items"] == []
