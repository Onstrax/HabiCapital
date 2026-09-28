"""Issue COP from the system omnibus account within the caller's transaction."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledger.domain.services import calculate_account_balance
from app.modules.ledger.infrastructure.models import (
    AccountModel, AccountType, AuditLogModel, LedgerEntryModel,
    TransactionModel, TransactionStatus, TransactionType, UserModel, UserRole,
)
from app.modules.ledger.use_cases.transfer_money import MAX_COP
from app.shared.exceptions import (
    AccountNotFoundException, BalanceLimitExceededException, OmnibusConfigurationException,
    SelfTransferForbiddenException,
)


async def execute_admin_topup(session: AsyncSession, admin_id: uuid.UUID,
                              target_account_id: uuid.UUID, amount: int,
                              concept: str, reference_id: str) -> tuple[TransactionModel, int]:
    """Create a single balanced ledger entry; only a persisted ADMIN may issue funds."""
    if isinstance(amount, bool) or not isinstance(amount, int) or not 0 < amount <= MAX_COP:
        raise ValueError("El monto debe ser un entero positivo dentro de BIGINT")
    if not concept.strip() or len(concept) > 255:
        raise ValueError("Concepto inválido")
    admin = await session.get(UserModel, admin_id)
    if admin is None or not admin.is_active or admin.role != UserRole.ADMIN:
        raise PermissionError("Solamente un administrador activo puede recargar saldo")
    omnibus_ids = (await session.execute(select(AccountModel.id).where(
        AccountModel.type == AccountType.SYSTEM_OMNIBUS))).scalars().all()
    if len(omnibus_ids) != 1:
        raise OmnibusConfigurationException("Se requiere una cuenta SYSTEM_OMNIBUS única")
    omnibus_id = omnibus_ids[0]
    if omnibus_id == target_account_id:
        raise SelfTransferForbiddenException("No se puede acreditar la cuenta ómnibus")
    ids = sorted([omnibus_id, target_account_id])
    accounts = (await session.execute(select(AccountModel).where(AccountModel.id.in_(ids))
                                      .order_by(AccountModel.id.asc()).with_for_update())).scalars().all()
    if len(accounts) != 2 or next(a for a in accounts if a.id == target_account_id).type != AccountType.USER_WALLET:
        raise AccountNotFoundException("Cuenta de usuario no encontrada")
    balance = await calculate_account_balance(target_account_id, session)
    if balance + amount > MAX_COP:
        raise BalanceLimitExceededException("El saldo objetivo excedería BIGINT")
    tx = TransactionModel(reference_id=reference_id, type=TransactionType.TOPUP,
                          status=TransactionStatus.SUCCESS, concept=concept)
    session.add(tx)
    await session.flush()
    session.add_all((
        LedgerEntryModel(transaction_id=tx.id, debit_account_id=omnibus_id,
                         credit_account_id=target_account_id, amount=amount),
        AuditLogModel(user_id=admin_id, action="ADMIN_TOPUP",
                      payload={"reference_id": reference_id, "amount": amount,
                               "target_account_id": str(target_account_id)}),
    ))
    await session.flush()
    return tx, balance + amount
