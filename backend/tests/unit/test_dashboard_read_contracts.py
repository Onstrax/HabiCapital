"""Read endpoints expose only wallet-scoped projections with no balance mutation."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.modules.ledger.adapters import controllers as ledger
from app.modules.ledger.infrastructure.models import PaymentRequestStatus, TransactionType, UserRole
from app.modules.payment_requests.adapters import controllers as charges

pytestmark = pytest.mark.asyncio


def request(path: str):
    return Request({"type": "http", "method": "GET", "path": path, "headers": []})


async def test_ledger_history_sign_and_scope(monkeypatch):
    actor = uuid.uuid4()
    wallet = SimpleNamespace(id=uuid.uuid4())
    entry = SimpleNamespace(debit_account_id=uuid.uuid4(), credit_account_id=wallet.id,
                            amount=50000, created_at=datetime.now(timezone.utc))
    tx = SimpleNamespace(reference_id="TOPUP-1", type=TransactionType.TOPUP, concept="Inicial")
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = SimpleNamespace(id=actor, is_active=True, role=UserRole.USER)
    session.execute.side_effect = [Mock(scalar_one_or_none=Mock(return_value=wallet)),
                                   Mock(all=Mock(return_value=[(entry, tx, "treasury", "user")]))]
    monkeypatch.setattr(ledger, "current_user_id", AsyncMock(return_value=actor))
    response = await ledger.get_movements(request("/api/v1/ledger/movements"), session)
    assert response.items[0].direction == "IN"
    assert response.items[0].amount == 50000
    assert response.items[0].counterparty_alias == "treasury"


async def test_pending_charge_projection_only_returns_query_rows(monkeypatch):
    actor = uuid.uuid4()
    model = SimpleNamespace(id=uuid.uuid4(), amount=1234, concept="Almuerzo",
                            status=PaymentRequestStatus.PENDING, created_at=datetime.now(timezone.utc))
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = SimpleNamespace(id=actor, is_active=True, role=UserRole.USER)
    session.execute.return_value = Mock(all=Mock(return_value=[(model, "sender", "recipient")]))
    monkeypatch.setattr(charges, "current_user_id", AsyncMock(return_value=actor))
    response = await charges.list_charges(request("/api/v1/charges"), PaymentRequestStatus.PENDING, session)
    assert response.items[0].status == "PENDING"
    assert response.items[0].requester_alias == "sender"
    assert response.items[0].amount == 1234
