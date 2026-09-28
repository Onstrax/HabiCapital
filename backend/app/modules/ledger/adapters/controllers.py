"""Authenticated HTTP endpoints for transfers and derived balances."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.adapters.controllers import (
    StrictSchema, api_error, current_user_id, limiter, lookup_rate_key,
)
from app.modules.ledger.domain.services import calculate_account_balance
from app.modules.ledger.infrastructure.models import AccountModel, UserModel
from app.modules.ledger.use_cases.transfer_money import execute_p2p_transfer_transactional
from app.shared.exceptions import (
    AccountNotFoundException, BalanceLimitExceededException, InsufficientFundsException,
    SelfTransferForbiddenException,
)

router = APIRouter(prefix="/api/v1")


class TransferRequest(StrictSchema):
    recipient_id: uuid.UUID = Field(strict=False)
    amount: int = Field(gt=0, le=2**63 - 1)
    concept: str = Field(min_length=1, max_length=255)


class TransferResponse(StrictSchema):
    reference_id: str
    status: str
    amount: int
    sender_alias: str
    recipient_alias: str
    concept: str
    created_at: datetime


class BalanceResponse(StrictSchema):
    account_id: uuid.UUID
    balance: int
    currency: str = "COP"


@router.post("/transfers/execute", response_model=TransferResponse, status_code=201)
@limiter.limit("10/minute", key_func=lookup_rate_key)
async def execute_transfer(request: Request, payload: TransferRequest,
                           session: AsyncSession = Depends(get_db)):
    sender_id = await current_user_id(request)
    if isinstance(sender_id, JSONResponse):
        return sender_id
    if sender_id == payload.recipient_id:
        return api_error(400, "SELF_TRANSFER_FORBIDDEN", "No se permiten auto-transferencias")

    try:
        async with session.begin():
            sender = await session.get(UserModel, sender_id)
            if sender is None or not sender.is_active:
                return api_error(401, "UNAUTHORIZED", "Token inválido")
            recipient = await session.get(UserModel, payload.recipient_id)
            if recipient is None or not recipient.is_active:
                return api_error(404, "RECIPIENT_NOT_FOUND", "Destinatario no encontrado")
            accounts = (await session.execute(select(AccountModel).where(
                AccountModel.user_id.in_([sender_id, payload.recipient_id])))).scalars().all()
            by_user = {account.user_id: account for account in accounts}
            if sender_id not in by_user or payload.recipient_id not in by_user:
                return api_error(404, "ACCOUNT_NOT_FOUND", "Cuenta no encontrada")

            tx = await execute_p2p_transfer_transactional(
                session=session, sender_account_id=by_user[sender_id].id,
                recipient_account_id=by_user[payload.recipient_id].id,
                amount=payload.amount, concept=payload.concept,
                reference_id="TRF-" + uuid.uuid4().hex,
            )
            response = TransferResponse(
                reference_id=tx.reference_id, status=tx.status.value,
                amount=payload.amount, sender_alias=sender.alias,
                recipient_alias=recipient.alias, concept=tx.concept,
                created_at=tx.created_at,
            )
    except InsufficientFundsException:
        return api_error(400, "INSUFFICIENT_FUNDS", "Saldo insuficiente para la transferencia")
    except BalanceLimitExceededException:
        return api_error(400, "BALANCE_LIMIT_EXCEEDED", "El saldo receptor excedería el límite")
    except SelfTransferForbiddenException:
        return api_error(400, "SELF_TRANSFER_FORBIDDEN", "No se permiten auto-transferencias")
    except AccountNotFoundException:
        return api_error(404, "ACCOUNT_NOT_FOUND", "Cuenta no encontrada")
    return response


@router.get("/ledger/balance", response_model=BalanceResponse)
async def get_balance(request: Request, session: AsyncSession = Depends(get_db)):
    user_id = await current_user_id(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    user = await session.get(UserModel, user_id)
    if user is None or not user.is_active:
        return api_error(401, "UNAUTHORIZED", "Token inválido")
    account = (await session.execute(select(AccountModel).where(
        AccountModel.user_id == user_id))).scalar_one_or_none()
    if account is None:
        return api_error(404, "ACCOUNT_NOT_FOUND", "Cuenta no encontrada")
    return BalanceResponse(account_id=account.id,
                           balance=await calculate_account_balance(account.id, session))
