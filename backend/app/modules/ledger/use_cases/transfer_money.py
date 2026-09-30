"""Pessimistically locked P2P transfer; caller owns BEGIN/COMMIT/ROLLBACK."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.ledger.domain.gmf_calculator import calculate_gmf_tax
from app.modules.ledger.domain.services import calculate_account_balance
from app.modules.ledger.infrastructure.models import (
    AccountModel, AccountType, AuditLogModel, LedgerEntryModel, TransactionModel,
    TransactionStatus, TransactionType,
)
from app.shared.exceptions import (
    AccountNotFoundException, BalanceLimitExceededException, InsufficientFundsException,
    SelfTransferForbiddenException, TaxAccountConfigurationException,
)

MAX_COP = 2**63 - 1


async def execute_p2p_transfer_transactional(
    session: AsyncSession,
    sender_account_id: uuid.UUID,
    recipient_account_id: uuid.UUID,
    amount: int,
    concept: str,
    reference_id: str,
    transaction_type: TransactionType = TransactionType.P2P_TRANSFER,
) -> TransactionModel:
    """Insert principal and GMF entries within the caller's open ACID transaction."""
    if isinstance(amount, bool) or not isinstance(amount, int) or not 0 < amount <= MAX_COP:
        raise ValueError("El monto debe ser un entero positivo dentro de BIGINT")
    if sender_account_id == recipient_account_id:
        raise SelfTransferForbiddenException("No se permiten auto-transferencias")
    if not concept.strip() or len(concept) > 255:
        raise ValueError("Concepto inválido")

    gmf_tax = calculate_gmf_tax(amount)
    total_required = amount + gmf_tax
    if total_required > MAX_COP:
        raise BalanceLimitExceededException("El monto más GMF excede BIGINT")
    tax_id = get_settings().SYSTEM_TAX_GMF_ACCOUNT_ID
    ids = sorted([sender_account_id, recipient_account_id, tax_id])
    locked = (await session.execute(
        select(AccountModel)
        .where(AccountModel.id.in_(ids))
        .order_by(AccountModel.id.asc())
        .with_for_update()
    )).scalars().all()
    accounts = {account.id: account for account in locked}
    if sender_account_id not in accounts or recipient_account_id not in accounts:
        raise AccountNotFoundException("Cuenta emisora o receptora no encontrada")
    if any(accounts[key].type != AccountType.USER_WALLET for key in (sender_account_id, recipient_account_id)):
        raise AccountNotFoundException("Las transferencias requieren dos billeteras de usuario")

    if tax_id not in accounts or accounts[tax_id].type != AccountType.SYSTEM_TAX_GMF or accounts[tax_id].user_id is not None:
        raise TaxAccountConfigurationException("Cuenta colectora GMF no configurada")
    balance = await calculate_account_balance(sender_account_id, session)
    if balance < total_required:
        raise InsufficientFundsException(balance, total_required, gmf_tax)
    recipient_balance = await calculate_account_balance(recipient_account_id, session)
    if recipient_balance + amount > MAX_COP:
        raise BalanceLimitExceededException("El saldo receptor excedería BIGINT")

    tax_balance = await calculate_account_balance(tax_id, session)
    if tax_balance + gmf_tax > MAX_COP:
        raise BalanceLimitExceededException("El saldo colector GMF excedería BIGINT")
    tx = TransactionModel(reference_id=reference_id, type=transaction_type, gmf_tax=gmf_tax,
                          status=TransactionStatus.SUCCESS, concept=concept)
    session.add(tx)
    await session.flush()
    session.add(LedgerEntryModel(transaction_id=tx.id, debit_account_id=sender_account_id,
                                 credit_account_id=recipient_account_id, amount=amount))
    session.add(LedgerEntryModel(transaction_id=tx.id, debit_account_id=sender_account_id,
                                 credit_account_id=tax_id, amount=gmf_tax))
    session.add(AuditLogModel(user_id=accounts[sender_account_id].user_id,
                              action=transaction_type.value,
                              payload={"reference_id": reference_id, "amount": amount,
                                       "gmf_tax": gmf_tax, "total_debit": total_required,
                                       "recipient_account_id": str(recipient_account_id)}))
    await session.flush()
    return tx
