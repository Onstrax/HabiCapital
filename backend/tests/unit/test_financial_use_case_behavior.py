"""Financial invariants at the use-case boundary, independent of HTTP tracing."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledger.infrastructure.models import (
    AccountType, AuditLogModel, LedgerEntryModel, PaymentRequestModel,
    PaymentRequestStatus, TransactionModel, TransactionStatus, TransactionType,
    UserRole,
)
from app.modules.ledger.use_cases import admin_topup, transfer_money
from app.modules.payment_requests.use_cases import charges
from app.shared.exceptions import (
    AccountNotFoundException, BalanceLimitExceededException, ChargeForbiddenException,
    ChargeNotFoundException, ChargeStateConflictException, InsufficientFundsException,
)

pytestmark = pytest.mark.asyncio
from app.core.config import DEFAULT_SYSTEM_TAX_GMF_ACCOUNT_ID

def tax_account():
    return SimpleNamespace(id=DEFAULT_SYSTEM_TAX_GMF_ACCOUNT_ID, user_id=None, type=AccountType.SYSTEM_TAX_GMF)

@pytest.fixture(autouse=True)
def tax_config(monkeypatch):
    monkeypatch.setattr(transfer_money, "get_settings", lambda: SimpleNamespace(
        SYSTEM_TAX_GMF_ACCOUNT_ID=DEFAULT_SYSTEM_TAX_GMF_ACCOUNT_ID))



def query_result(rows=None, row=None):
    result = Mock()
    result.scalars.return_value.all.return_value = rows
    result.scalar_one_or_none.return_value = row
    return result


async def test_transfer_locks_three_accounts_in_uuid_order_and_posts_two_balanced_entries(monkeypatch):
    sender_id, recipient_id = uuid.UUID(int=2), uuid.UUID(int=1)
    sender_user = uuid.uuid4()
    sender = SimpleNamespace(id=sender_id, user_id=sender_user, type=AccountType.USER_WALLET)
    recipient = SimpleNamespace(id=recipient_id, user_id=uuid.uuid4(), type=AccountType.USER_WALLET)
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = query_result(rows=[recipient, sender, tax_account()])
    monkeypatch.setattr(transfer_money, "calculate_account_balance",
                        AsyncMock(side_effect=[50200, 0, 0]))

    tx = await transfer_money.execute_p2p_transfer_transactional(
        session, sender_id, recipient_id, 50000, "Test transfer", "TRF-UNIT",
    )

    sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert "ORDER BY accounts.id ASC FOR UPDATE" in sql
    assert tx.type == TransactionType.P2P_TRANSFER
    assert tx.status == TransactionStatus.SUCCESS
    entries = [call.args[0] for call in session.add.call_args_list]
    ledger = next(item for item in entries if isinstance(item, LedgerEntryModel))
    audit = next(item for item in entries if isinstance(item, AuditLogModel))
    assert (ledger.debit_account_id, ledger.credit_account_id, ledger.amount) == (
        sender_id, recipient_id, 50000,
    )
    fee = [item for item in entries if isinstance(item, LedgerEntryModel)][1]
    assert (fee.debit_account_id, fee.credit_account_id, fee.amount) == (sender_id, DEFAULT_SYSTEM_TAX_GMF_ACCOUNT_ID, 200)
    assert tx.gmf_tax == 200
    assert audit.user_id == sender_user
    assert session.flush.await_count == 2


@pytest.mark.parametrize("balance,recipient_balance,expected", [
    (49999, 0, InsufficientFundsException),
    (50200, 2**63 - 1, BalanceLimitExceededException),
])
async def test_transfer_fails_before_inserting_any_financial_row(
    monkeypatch, balance, recipient_balance, expected,
):
    sender_id, recipient_id = uuid.uuid4(), uuid.uuid4()
    accounts = [SimpleNamespace(id=sender_id, user_id=uuid.uuid4(), type=AccountType.USER_WALLET),
                SimpleNamespace(id=recipient_id, user_id=uuid.uuid4(), type=AccountType.USER_WALLET)]
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = query_result(rows=accounts + [tax_account()])
    monkeypatch.setattr(transfer_money, "calculate_account_balance",
                        AsyncMock(side_effect=[balance, recipient_balance]))
    with pytest.raises(expected):
        await transfer_money.execute_p2p_transfer_transactional(
            session, sender_id, recipient_id, 50000, "Test", "TRF-REJECT",
        )
    session.add.assert_not_called()


async def test_transfer_rejects_account_removed_before_the_lock():
    sender_id, recipient_id = uuid.uuid4(), uuid.uuid4()
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = query_result(rows=[SimpleNamespace(id=sender_id)])
    with pytest.raises(AccountNotFoundException):
        await transfer_money.execute_p2p_transfer_transactional(
            session, sender_id, recipient_id, 1, "Test", "TRF-MISSING",
        )
    session.add.assert_not_called()


async def test_transfer_refuses_to_use_admin_omnibus_as_sender(monkeypatch):
    sender_id, recipient_id = uuid.uuid4(), uuid.uuid4()
    accounts = [SimpleNamespace(id=sender_id, user_id=uuid.uuid4(), type=AccountType.SYSTEM_OMNIBUS),
                SimpleNamespace(id=recipient_id, user_id=uuid.uuid4(), type=AccountType.USER_WALLET)]
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = query_result(rows=accounts + [tax_account()])
    calculate = AsyncMock(return_value=100000)
    monkeypatch.setattr(transfer_money, "calculate_account_balance", calculate)
    with pytest.raises(AccountNotFoundException):
        await transfer_money.execute_p2p_transfer_transactional(
            session, sender_id, recipient_id, 50000, "Test", "TRF-OMNIBUS")
    session.add.assert_not_called()
    calculate.assert_not_awaited()


async def test_admin_topup_issues_exact_amount_from_omnibus_under_ordered_locks(monkeypatch):
    admin_id, target_id, omnibus_id = uuid.uuid4(), uuid.UUID(int=1), uuid.UUID(int=2)
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = SimpleNamespace(role=UserRole.ADMIN, is_active=True)
    session.execute.side_effect = [query_result(rows=[omnibus_id]), query_result(rows=[
        SimpleNamespace(id=target_id, type=AccountType.USER_WALLET),
        SimpleNamespace(id=omnibus_id, type=AccountType.SYSTEM_OMNIBUS),
    ])]
    monkeypatch.setattr(admin_topup, "calculate_account_balance", AsyncMock(return_value=100))

    tx, new_balance = await admin_topup.execute_admin_topup(
        session, admin_id, target_id, 50000, "Issue COP", "TOPUP-UNIT",
    )

    sql = str(session.execute.await_args_list[1].args[0].compile(dialect=postgresql.dialect()))
    assert "ORDER BY accounts.id ASC FOR UPDATE" in sql
    assert tx.type == TransactionType.TOPUP and new_balance == 50100
    ledger, audit = session.add_all.call_args.args[0]
    assert (ledger.debit_account_id, ledger.credit_account_id, ledger.amount) == (
        omnibus_id, target_id, 50000,
    )
    assert audit.user_id == admin_id


async def test_create_charge_only_persists_pending_request():
    session = AsyncMock(spec=AsyncSession)
    requester_id, payer_id = uuid.uuid4(), uuid.uuid4()
    charge = await charges.create_charge_request(session, requester_id, payer_id, 25000, "Dinner")
    assert isinstance(charge, PaymentRequestModel)
    assert charge.status == PaymentRequestStatus.PENDING
    assert (charge.requester_account_id, charge.payer_account_id, charge.amount) == (
        requester_id, payer_id, 25000,
    )
    session.add.assert_called_once_with(charge)
    session.flush.assert_awaited_once()


def locked_charge_fixture():
    payer_id, requester_id = uuid.uuid4(), uuid.uuid4()
    payer_account, requester_account = uuid.uuid4(), uuid.uuid4()
    charge = PaymentRequestModel(id=uuid.uuid4(), payer_account_id=payer_account,
                                 requester_account_id=requester_account, amount=25000,
                                 concept="Dinner", status=PaymentRequestStatus.PENDING)
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = query_result(row=charge)
    session.get.side_effect = lambda _, account_id: SimpleNamespace(
        user_id=payer_id if account_id == payer_account else requester_id,
        type=AccountType.USER_WALLET,
    )
    return session, charge, payer_id, requester_id


async def test_charge_payment_moves_money_and_completes_once(monkeypatch):
    session, charge, payer_id, _ = locked_charge_fixture()
    transaction = TransactionModel(reference_id="TRF-CHARGE", type=TransactionType.PAYMENT_REQUEST_PAYMENT,
                                   status=TransactionStatus.SUCCESS, concept="Dinner")
    transfer = AsyncMock(return_value=transaction)
    monkeypatch.setattr(charges, "execute_p2p_transfer_transactional", transfer)
    result = await charges.process_charge_payment(session, charge.id, payer_id, "TRF-CHARGE")
    assert result is transaction
    assert charge.status == PaymentRequestStatus.COMPLETED
    assert transfer.await_args.kwargs["transaction_type"] == TransactionType.PAYMENT_REQUEST_PAYMENT
    assert transfer.await_args.kwargs["sender_account_id"] == charge.payer_account_id
    assert transfer.await_args.kwargs["recipient_account_id"] == charge.requester_account_id
    session.flush.assert_awaited_once()


async def test_charge_failed_payment_audits_without_changing_pending_state(monkeypatch):
    session, charge, payer_id, _ = locked_charge_fixture()
    monkeypatch.setattr(charges, "execute_p2p_transfer_transactional",
                        AsyncMock(side_effect=InsufficientFundsException(0, charge.amount)))
    result = await charges.process_charge_payment(session, charge.id, payer_id, "TRF-FAILED")
    assert result.current_balance == 0 and result.required_amount == 25000
    assert charge.status == PaymentRequestStatus.PENDING
    audit = session.add.call_args.args[0]
    assert isinstance(audit, AuditLogModel)
    assert audit.action == "PAYMENT_REQUEST_INSUFFICIENT_FUNDS"
    session.flush.assert_awaited_once()


async def test_charge_reject_and_cancel_are_role_scoped_terminal_transitions():
    session, charge, payer_id, requester_id = locked_charge_fixture()
    result = await charges.reject_charge(session, charge.id, payer_id)
    assert result.status == PaymentRequestStatus.REJECTED
    charge.status = PaymentRequestStatus.PENDING
    result = await charges.cancel_charge(session, charge.id, requester_id)
    assert result.status == PaymentRequestStatus.CANCELLED
    assert session.flush.await_count == 2


@pytest.mark.parametrize("change", ["missing", "wrong_actor", "terminal"])
async def test_charge_fails_closed_when_missing_unauthorized_or_terminal(change):
    session, charge, payer_id, _ = locked_charge_fixture()
    expected = {
        "missing": ChargeNotFoundException,
        "wrong_actor": ChargeForbiddenException,
        "terminal": ChargeStateConflictException,
    }[change]
    if change == "missing":
        session.execute.return_value = query_result(row=None)
    elif change == "wrong_actor":
        session.get.side_effect = None
        session.get.return_value = SimpleNamespace(user_id=uuid.uuid4(), type=AccountType.USER_WALLET)
    else:
        charge.status = PaymentRequestStatus.COMPLETED
    with pytest.raises(expected):
        await charges.process_charge_payment(session, charge.id, payer_id, "TRF-NOOP")
    session.flush.assert_not_awaited()
