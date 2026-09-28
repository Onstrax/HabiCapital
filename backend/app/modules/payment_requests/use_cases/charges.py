"""Deterministic charge transitions; the caller commits the ACID transaction."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledger.infrastructure.models import (
    AccountModel, AuditLogModel, PaymentRequestModel, PaymentRequestStatus,
    TransactionType,
)
from app.modules.ledger.use_cases.transfer_money import (
    MAX_COP, execute_p2p_transfer_transactional,
)
from app.shared.exceptions import (
    ChargeForbiddenException, ChargeNotFoundException, ChargeStateConflictException,
    InsufficientFundsException,
)


@dataclass(frozen=True)
class InsufficientChargePayment:
    current_balance: int
    required_amount: int


async def create_charge_request(session: AsyncSession, requester_account_id: uuid.UUID,
                                payer_account_id: uuid.UUID, amount: int,
                                concept: str) -> PaymentRequestModel:
    if isinstance(amount, bool) or not isinstance(amount, int) or not 0 < amount <= MAX_COP:
        raise ValueError("Monto inválido")
    if requester_account_id == payer_account_id:
        raise ValueError("No se permiten autocobros")
    if not concept.strip() or len(concept) > 255:
        raise ValueError("Concepto inválido")
    charge = PaymentRequestModel(requester_account_id=requester_account_id,
                                 payer_account_id=payer_account_id, amount=amount,
                                 concept=concept, status=PaymentRequestStatus.PENDING)
    session.add(charge)
    await session.flush()
    return charge


async def _locked_pending_charge(session: AsyncSession, charge_id: uuid.UUID,
                                 actor_id: uuid.UUID, actor_side: str) -> PaymentRequestModel:
    charge = (await session.execute(select(PaymentRequestModel).where(
        PaymentRequestModel.id == charge_id).with_for_update())).scalar_one_or_none()
    if charge is None:
        raise ChargeNotFoundException("Cobro no encontrado")
    account_id = charge.payer_account_id if actor_side == "payer" else charge.requester_account_id
    account = await session.get(AccountModel, account_id)
    if account is None or account.user_id != actor_id:
        raise ChargeForbiddenException("Acción no permitida para este cobro")
    if charge.status != PaymentRequestStatus.PENDING:
        raise ChargeStateConflictException("El cobro está en estado terminal")
    return charge


async def process_charge_payment(session: AsyncSession, charge_id: uuid.UUID,
                                 payer_id: uuid.UUID, reference_id: str):
    charge = await _locked_pending_charge(session, charge_id, payer_id, "payer")
    try:
        tx = await execute_p2p_transfer_transactional(
            session=session, sender_account_id=charge.payer_account_id,
            recipient_account_id=charge.requester_account_id,
            amount=charge.amount, concept=charge.concept, reference_id=reference_id,
            transaction_type=TransactionType.PAYMENT_REQUEST_PAYMENT,
        )
    except InsufficientFundsException as error:
        # The transfer has not inserted any financial rows at this point.
        session.add(AuditLogModel(user_id=payer_id,
                                  action="PAYMENT_REQUEST_INSUFFICIENT_FUNDS",
                                  payload={"charge_id": str(charge.id),
                                           "current_balance": error.current_balance,
                                           "required_amount": error.required_amount}))
        await session.flush()
        return InsufficientChargePayment(error.current_balance, error.required_amount)
    charge.status = PaymentRequestStatus.COMPLETED
    await session.flush()
    return tx


async def reject_charge(session: AsyncSession, charge_id: uuid.UUID,
                        payer_id: uuid.UUID) -> PaymentRequestModel:
    charge = await _locked_pending_charge(session, charge_id, payer_id, "payer")
    charge.status = PaymentRequestStatus.REJECTED
    await session.flush()
    return charge


async def cancel_charge(session: AsyncSession, charge_id: uuid.UUID,
                        requester_id: uuid.UUID) -> PaymentRequestModel:
    charge = await _locked_pending_charge(session, charge_id, requester_id, "requester")
    charge.status = PaymentRequestStatus.CANCELLED
    await session.flush()
    return charge
