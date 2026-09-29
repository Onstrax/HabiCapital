"""Controller contracts keep actor, account and ledger use cases aligned."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.modules.ledger.adapters import controllers as ledger
from app.modules.ledger.infrastructure.models import PaymentRequestStatus, TransactionStatus, UserRole
from app.modules.payment_requests.adapters import controllers as charges
from app.modules.payment_requests.use_cases.charges import InsufficientChargePayment

pytestmark = pytest.mark.asyncio


def request(path: str, method: str = "POST") -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": []})


def query_result(*, row=None, rows=None):
    result = Mock()
    result.scalar_one_or_none.return_value = row
    result.scalars.return_value.all.return_value = rows
    return result


async def test_transfer_controller_passes_user_wallet_ids_and_formats_success(monkeypatch):
    sender_id, recipient_id = uuid.uuid4(), uuid.uuid4()
    sender_account, recipient_account = uuid.uuid4(), uuid.uuid4()
    sender = SimpleNamespace(id=sender_id, is_active=True, alias="sender", role=UserRole.USER)
    recipient = SimpleNamespace(id=recipient_id, is_active=True, alias="recipient", role=UserRole.USER)
    session = AsyncMock(spec=AsyncSession)
    session.get.side_effect = [sender, recipient]
    session.execute.return_value = query_result(rows=[
        SimpleNamespace(user_id=sender_id, id=sender_account),
        SimpleNamespace(user_id=recipient_id, id=recipient_account),
    ])
    tx = SimpleNamespace(reference_id="TRF-CONTRACT", status=TransactionStatus.SUCCESS,
                         concept="Lunch", created_at=datetime.now(timezone.utc))
    transfer = AsyncMock(return_value=tx)
    monkeypatch.setattr(ledger, "current_user_id", AsyncMock(return_value=sender_id))
    monkeypatch.setattr(ledger, "execute_p2p_transfer_transactional", transfer)

    response = await ledger.execute_transfer(
        request("/api/v1/transfers/execute"),
        ledger.TransferRequest(recipient_id=recipient_id, amount=50000, concept="Lunch"), session,
    )
    assert response.reference_id == "TRF-CONTRACT" and response.status == "SUCCESS"
    assert response.sender_alias == "sender" and response.recipient_alias == "recipient"
    assert response.amount == 50000
    assert transfer.await_args.kwargs["sender_account_id"] == sender_account
    assert transfer.await_args.kwargs["recipient_account_id"] == recipient_account


async def test_admin_cannot_execute_user_wallet_transfer(monkeypatch):
    actor_id, recipient_id = uuid.uuid4(), uuid.uuid4()
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = SimpleNamespace(id=actor_id, is_active=True,
                                               role=UserRole.ADMIN)
    monkeypatch.setattr(ledger, "current_user_id", AsyncMock(return_value=actor_id))
    transfer = AsyncMock()
    monkeypatch.setattr(ledger, "execute_p2p_transfer_transactional", transfer)
    response = await ledger.execute_transfer(
        request("/api/v1/transfers/execute"),
        ledger.TransferRequest(recipient_id=recipient_id, amount=50000, concept="Test"), session)
    assert response.status_code == 401
    transfer.assert_not_awaited()


async def test_balance_controller_derives_balance_for_authenticated_wallet(monkeypatch):
    actor = uuid.uuid4()
    account = SimpleNamespace(id=uuid.uuid4(), user_id=actor)
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = SimpleNamespace(id=actor, is_active=True)
    session.execute.return_value = query_result(row=account)
    monkeypatch.setattr(ledger, "current_user_id", AsyncMock(return_value=actor))
    calculate = AsyncMock(return_value=50000)
    monkeypatch.setattr(ledger, "calculate_account_balance", calculate)

    response = await ledger.get_balance(request("/api/v1/ledger/balance", "GET"), session)
    assert response.account_id == account.id and response.balance == 50000
    calculate.assert_awaited_once_with(account.id, session)


async def test_admin_topup_controller_uses_persisted_role_and_target_wallet(monkeypatch):
    admin_id, target_id, target_account_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = SimpleNamespace(id=admin_id, is_active=True, role=UserRole.ADMIN)
    session.execute.side_effect = [
        query_result(row=SimpleNamespace(id=target_id, alias="recipient")),
        query_result(row=SimpleNamespace(id=target_account_id, user_id=target_id)),
    ]
    tx = SimpleNamespace(reference_id="TOPUP-CONTRACT", created_at=datetime.now(timezone.utc))
    topup = AsyncMock(return_value=(tx, 50000))
    monkeypatch.setattr(ledger, "current_user_id", AsyncMock(return_value=admin_id))
    monkeypatch.setattr(ledger, "execute_admin_topup", topup)

    response = await ledger.admin_topup(
        request("/api/v1/admin/topup"),
        ledger.TopupRequest(target_user_alias="recipient", amount=50000, concept="Funding"), session,
    )
    assert response.reference_id == "TOPUP-CONTRACT"
    assert response.new_target_balance == 50000 and response.target_alias == "recipient"
    assert topup.await_args.args[1:4] == (admin_id, target_account_id, 50000)


async def test_charge_controller_creates_pending_request_for_wallets(monkeypatch):
    requester_id, payer_id = uuid.uuid4(), uuid.uuid4()
    requester_account, payer_account = uuid.uuid4(), uuid.uuid4()
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = SimpleNamespace(id=requester_id, is_active=True, alias="requester", role=UserRole.USER)
    session.execute.side_effect = [
        query_result(row=SimpleNamespace(id=payer_id, is_active=True, alias="payer")),
        query_result(rows=[SimpleNamespace(user_id=requester_id, id=requester_account),
                           SimpleNamespace(user_id=payer_id, id=payer_account)]),
    ]
    charge = SimpleNamespace(id=uuid.uuid4(), amount=25000, concept="Dinner",
                             status=PaymentRequestStatus.PENDING, created_at=datetime.now(timezone.utc))
    create = AsyncMock(return_value=charge)
    monkeypatch.setattr(charges, "current_user_id", AsyncMock(return_value=requester_id))
    monkeypatch.setattr(charges, "create_charge_request", create)

    response = await charges.create_charge(
        request("/api/v1/charges"),
        charges.ChargeRequest(payer_alias="payer", amount=25000, concept="Dinner"), session,
    )
    assert response.id == charge.id and response.status == "PENDING"
    assert response.requester_alias == "requester" and response.payer_alias == "payer"
    assert create.await_args.args[1:4] == (requester_account, payer_account, 25000)


async def test_charge_payment_controller_returns_paid_or_pending_audit_contract(monkeypatch):
    payer_id, charge_id = uuid.uuid4(), uuid.uuid4()
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = SimpleNamespace(id=payer_id, is_active=True, role=UserRole.USER)
    monkeypatch.setattr(charges, "current_user_id", AsyncMock(return_value=payer_id))
    paid = AsyncMock(return_value=SimpleNamespace(reference_id="TRF-PAID",
                                                  created_at=datetime.now(timezone.utc)))
    monkeypatch.setattr(charges, "process_charge_payment", paid)
    response = await charges.pay_charge(request(f"/api/v1/charges/{charge_id}/pay"), charge_id, session)
    assert response.charge_id == charge_id and response.status == "COMPLETED"
    assert response.transaction_reference == "TRF-PAID"

    paid.return_value = InsufficientChargePayment(current_balance=0, required_amount=25000)
    failure = await charges.pay_charge(request(f"/api/v1/charges/{charge_id}/pay"), charge_id, session)
    assert failure.status_code == 400
    assert b'"charge_status":"PENDING"' in failure.body


async def test_reject_and_cancel_controllers_return_terminal_states(monkeypatch):
    actor_id, charge_id = uuid.uuid4(), uuid.uuid4()
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = SimpleNamespace(id=actor_id, is_active=True, role=UserRole.USER)
    monkeypatch.setattr(charges, "current_user_id", AsyncMock(return_value=actor_id))
    reject = AsyncMock(return_value=SimpleNamespace(id=charge_id, status=PaymentRequestStatus.REJECTED))
    cancel = AsyncMock(return_value=SimpleNamespace(id=charge_id, status=PaymentRequestStatus.CANCELLED))
    monkeypatch.setattr(charges, "reject_charge", reject)
    monkeypatch.setattr(charges, "cancel_charge", cancel)

    rejected = await charges.reject(request(f"/api/v1/charges/{charge_id}/reject"), charge_id, session)
    cancelled = await charges.cancel(request(f"/api/v1/charges/{charge_id}/cancel"), charge_id, session)
    assert rejected.status == "REJECTED" and cancelled.status == "CANCELLED"
    reject.assert_awaited_once_with(session, charge_id, actor_id)
    cancel.assert_awaited_once_with(session, charge_id, actor_id)
