"""Charge HTTP contracts and role checked state transitions."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.database import get_db
from app.modules.identity.adapters.controllers import (
    StrictSchema, api_error, current_user_id, limiter, lookup_rate_key,
)
from app.modules.ledger.infrastructure.models import (
    AccountModel, AccountType, PaymentRequestModel, PaymentRequestStatus, UserModel,
)
from app.modules.payment_requests.use_cases.charges import (
    InsufficientChargePayment, cancel_charge, create_charge_request,
    process_charge_payment, reject_charge,
)
from app.shared.exceptions import (
    BalanceLimitExceededException, ChargeForbiddenException,
    ChargeNotFoundException, ChargeStateConflictException,
)
from app.shared.utils.security_utils import sanitize_alias

router = APIRouter(prefix="/api/v1/charges")


class ChargeRequest(StrictSchema):
    payer_alias: str
    amount: int = Field(gt=0, le=2**63 - 1)
    concept: str = Field(min_length=1, max_length=255)


class ChargeResponse(StrictSchema):
    id: uuid.UUID
    requester_alias: str
    payer_alias: str
    amount: int
    concept: str
    status: str
    created_at: datetime


class ChargesResponse(StrictSchema):
    items: list[ChargeResponse]


class PaidResponse(StrictSchema):
    charge_id: uuid.UUID
    status: str
    transaction_reference: str
    paid_at: datetime


class TransitionResponse(StrictSchema):
    charge_id: uuid.UUID
    status: str


def charge_error(exc: Exception) -> JSONResponse:
    if isinstance(exc, ChargeNotFoundException):
        return api_error(404, "CHARGE_NOT_FOUND", "Cobro no encontrado")
    if isinstance(exc, ChargeForbiddenException):
        return api_error(403, "FORBIDDEN", "No autorizado para este cobro")
    if isinstance(exc, ChargeStateConflictException):
        return api_error(409, "CHARGE_STATE_CONFLICT", "El cobro está en estado terminal")
    return api_error(400, "BALANCE_LIMIT_EXCEEDED", "El saldo receptor excedería el límite")


@router.get("", response_model=ChargesResponse)
async def list_charges(request: Request, status: PaymentRequestStatus = Query(PaymentRequestStatus.PENDING),
                       session: AsyncSession = Depends(get_db)):
    payer_id = await current_user_id(request)
    if isinstance(payer_id, JSONResponse):
        return payer_id
    user = await session.get(UserModel, payer_id)
    if user is None or not user.is_active:
        return api_error(401, "UNAUTHORIZED", "Token inválido")
    requester_account, payer_account = aliased(AccountModel), aliased(AccountModel)
    requester, payer = aliased(UserModel), aliased(UserModel)
    rows = (await session.execute(
        select(PaymentRequestModel, requester.alias, payer.alias)
        .join(requester_account, requester_account.id == PaymentRequestModel.requester_account_id)
        .join(requester, requester.id == requester_account.user_id)
        .join(payer_account, payer_account.id == PaymentRequestModel.payer_account_id)
        .join(payer, payer.id == payer_account.user_id)
        .where(payer_account.user_id == payer_id, PaymentRequestModel.status == status)
        .order_by(PaymentRequestModel.created_at.desc(), PaymentRequestModel.id.desc())
        .limit(50)
    )).all()
    return ChargesResponse(items=[ChargeResponse(
        id=charge.id, requester_alias=requester_alias, payer_alias=payer_alias,
        amount=charge.amount, concept=charge.concept, status=charge.status.value,
        created_at=charge.created_at,
    ) for charge, requester_alias, payer_alias in rows])


@router.post("", response_model=ChargeResponse, status_code=201)
@limiter.limit("15/minute", key_func=lookup_rate_key)
async def create_charge(request: Request, payload: ChargeRequest,
                        session: AsyncSession = Depends(get_db)):
    requester_id = await current_user_id(request)
    if isinstance(requester_id, JSONResponse):
        return requester_id
    try:
        alias = sanitize_alias(payload.payer_alias)
    except ValueError:
        return api_error(422, "VALIDATION_ERROR", "Alias inválido")
    async with session.begin():
        requester = await session.get(UserModel, requester_id)
        if requester is None or not requester.is_active:
            return api_error(401, "UNAUTHORIZED", "Token inválido")
        payer = (await session.execute(select(UserModel).where(
            UserModel.alias == alias, UserModel.is_active.is_(True)))).scalar_one_or_none()
        if payer is None:
            return api_error(404, "PAYER_NOT_FOUND", "Pagador no encontrado")
        if payer.id == requester.id:
            return api_error(400, "SELF_CHARGE_FORBIDDEN", "No se permiten autocobros")
        accounts = (await session.execute(select(AccountModel).where(
            AccountModel.user_id.in_([requester_id, payer.id]),
            AccountModel.type == AccountType.USER_WALLET))).scalars().all()
        by_user = {account.user_id: account for account in accounts}
        if requester_id not in by_user or payer.id not in by_user:
            return api_error(404, "ACCOUNT_NOT_FOUND", "Cuenta no encontrada")
        charge = await create_charge_request(session, by_user[requester_id].id,
                                             by_user[payer.id].id, payload.amount,
                                             payload.concept)
        return ChargeResponse(id=charge.id, requester_alias=requester.alias,
                              payer_alias=payer.alias, amount=charge.amount,
                              concept=charge.concept, status=charge.status.value,
                              created_at=charge.created_at)


@router.post("/{charge_id}/pay", response_model=PaidResponse)
@limiter.limit("15/minute", key_func=lookup_rate_key)
async def pay_charge(request: Request, charge_id: uuid.UUID,
                     session: AsyncSession = Depends(get_db)):
    payer_id = await current_user_id(request)
    if isinstance(payer_id, JSONResponse):
        return payer_id
    try:
        async with session.begin():
            actor = await session.get(UserModel, payer_id)
            if actor is None or not actor.is_active:
                return api_error(401, "UNAUTHORIZED", "Token inválido")
            outcome = await process_charge_payment(session, charge_id, payer_id,
                                                   "TRF-" + uuid.uuid4().hex)
            if isinstance(outcome, InsufficientChargePayment):
                response = JSONResponse(status_code=400, content={
                    "code": "INSUFFICIENT_FUNDS_FOR_PAYMENT_REQUEST",
                    "message": "Saldo insuficiente para completar este pago. El cobro se mantendrá en estado PENDING.",
                    "details": {"current_balance": outcome.current_balance,
                                "required_amount": outcome.required_amount,
                                "charge_status": "PENDING"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            else:
                response = PaidResponse(charge_id=charge_id, status="COMPLETED",
                                        transaction_reference=outcome.reference_id,
                                        paid_at=outcome.created_at)
    except (ChargeNotFoundException, ChargeForbiddenException,
            ChargeStateConflictException, BalanceLimitExceededException) as exc:
        return charge_error(exc)
    return response


@router.post("/{charge_id}/reject", response_model=TransitionResponse)
@limiter.limit("15/minute", key_func=lookup_rate_key)
async def reject(request: Request, charge_id: uuid.UUID,
                 session: AsyncSession = Depends(get_db)):
    payer_id = await current_user_id(request)
    if isinstance(payer_id, JSONResponse):
        return payer_id
    try:
        async with session.begin():
            actor = await session.get(UserModel, payer_id)
            if actor is None or not actor.is_active:
                return api_error(401, "UNAUTHORIZED", "Token inválido")
            charge = await reject_charge(session, charge_id, payer_id)
            response = TransitionResponse(charge_id=charge.id, status=charge.status.value)
    except (ChargeNotFoundException, ChargeForbiddenException, ChargeStateConflictException) as exc:
        return charge_error(exc)
    return response


@router.post("/{charge_id}/cancel", response_model=TransitionResponse)
@limiter.limit("15/minute", key_func=lookup_rate_key)
async def cancel(request: Request, charge_id: uuid.UUID,
                 session: AsyncSession = Depends(get_db)):
    requester_id = await current_user_id(request)
    if isinstance(requester_id, JSONResponse):
        return requester_id
    try:
        async with session.begin():
            actor = await session.get(UserModel, requester_id)
            if actor is None or not actor.is_active:
                return api_error(401, "UNAUTHORIZED", "Token inválido")
            charge = await cancel_charge(session, charge_id, requester_id)
            response = TransitionResponse(charge_id=charge.id, status=charge.status.value)
    except (ChargeNotFoundException, ChargeForbiddenException, ChargeStateConflictException) as exc:
        return charge_error(exc)
    return response
