"""Validate the whole recipient set before inserting any group charge."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.field_encryption import blind_index
from app.modules.ledger.infrastructure.models import (
    AccountModel, AccountType, PaymentRequestModel, PaymentRequestStatus, UserModel, UserRole,
)
from app.modules.payment_requests.domain.split_calculator import (
    RecipientAllocation, calculate_exact_cop_split,
)


class GroupChargeError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RequestedRecipient:
    alias: str
    percentage: float
    is_locked: bool


async def create_group_charge(session: AsyncSession, requester_id: uuid.UUID,
                              total_amount: int, concept: str, recipients: list[RequestedRecipient]):
    """The caller owns one DB transaction covering lookups, validation, and insertion."""
    requester = await session.get(UserModel, requester_id)
    if requester is None or not requester.is_active or requester.role != UserRole.USER:
        raise GroupChargeError("UNAUTHORIZED", "Token inválido")
    aliases = [row.alias for row in recipients]
    if requester.alias in aliases:
        raise GroupChargeError("SELF_CHARGE_FORBIDDEN", "No se permiten autocobros")
    hashes = [blind_index(alias, "users.alias") for alias in aliases]
    payers = (await session.execute(select(UserModel).where(
        UserModel.alias_blind_index.in_(hashes), UserModel.is_active.is_(True),
        UserModel.role == UserRole.USER))).scalars().all()
    by_alias = {user.alias: user for user in payers}
    if set(by_alias) != set(aliases):
        raise GroupChargeError("PAYER_NOT_FOUND", "Uno o más aliases no corresponden a usuarios activos")
    accounts = (await session.execute(select(AccountModel).where(
        AccountModel.user_id.in_([requester_id] + [user.id for user in payers]),
        AccountModel.type == AccountType.USER_WALLET))).scalars().all()
    by_user = {account.user_id: account for account in accounts}
    if len(by_user) != len(payers) + 1:
        raise GroupChargeError("ACCOUNT_NOT_FOUND", "Una o más cuentas no están disponibles")
    allocation = [RecipientAllocation(by_user[by_alias[row.alias].id].id,
                                      row.percentage, row.is_locked)
                  for row in recipients]
    try:
        shares = calculate_exact_cop_split(total_amount, allocation)
    except ValueError as exc:
        raise GroupChargeError("INVALID_SPLIT", str(exc)) from exc
    group_id = uuid.uuid4()
    rows = [PaymentRequestModel(
        requester_account_id=by_user[requester_id].id, payer_account_id=account_id,
        amount=amount, percentage=Decimal(str(percentage)), group_id=group_id,
        concept=concept, status=PaymentRequestStatus.PENDING,
    ) for account_id, amount, percentage in shares]
    session.add_all(rows)
    await session.flush()
    return group_id, list(zip(rows, (by_alias[alias] for alias in aliases)))
