"""Charge HTTP contracts and role checked state transitions."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field, computed_field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.database import get_db
from app.modules.ledger.domain.gmf_calculator import calculate_gmf_tax
from app.core.field_encryption import blind_index
from app.core.openapi_security import bearer_auth, financial_key_header
from app.modules.identity.adapters.controllers import (
    StrictSchema, api_error, current_user_id, limiter, lookup_rate_key, read_limit,
)
from app.modules.ledger.infrastructure.models import (
    AccountModel, AccountType, PaymentRequestModel, PaymentRequestStatus, UserModel, UserRole,
)
from app.modules.payment_requests.use_cases.charges import (
    InsufficientChargePayment, cancel_charge, create_charge_request,
    process_charge_payment, reject_charge,
)
from app.modules.payment_requests.adapters.schemas import (
    CreateGroupPaymentRequestSchema, CreatedPaymentRequestResponseSchema,
    CreatedPaymentRequestsSchema, GroupPaymentRequestResponseSchema,
)
from app.modules.payment_requests.use_cases.create_group_charge import (
    GroupChargeError, RequestedRecipient, create_group_charge,
)
from app.shared.exceptions import (
    BalanceLimitExceededException, ChargeForbiddenException,
    ChargeNotFoundException, ChargeStateConflictException, TaxAccountConfigurationException,
)
from app.shared.utils.security_utils import mask_full_name, sanitize_alias

router = APIRouter(prefix="/api/v1/charges", dependencies=[Depends(bearer_auth)])


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


    @computed_field
    @property
    def gmf_tax(self) -> int:
        return calculate_gmf_tax(self.amount)

    @computed_field
    @property
    def total_debit(self) -> int:
        return self.amount + self.gmf_tax


class ChargesResponse(StrictSchema):
    items: list[ChargeResponse]


class PaidResponse(StrictSchema):
    amount: int
    gmf_tax: int
    total_debit: int
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


async def _received_charges(request: Request, status: PaymentRequestStatus,
                            session: AsyncSession):
    payer_id = await current_user_id(request)
    if isinstance(payer_id, JSONResponse):
        return payer_id
    user = await session.get(UserModel, payer_id)
    if user is None or not user.is_active:
        return api_error(401, "UNAUTHORIZED", "Token inválido")
    if user.role != UserRole.USER:
        return api_error(403, "FORBIDDEN", "Esta vista es exclusiva para usuarios")
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


@router.get("", response_model=ChargesResponse)
@read_limit
async def list_charges(request: Request, status: PaymentRequestStatus = Query(PaymentRequestStatus.PENDING),
                       session: AsyncSession = Depends(get_db)):
    return await _received_charges(request, status, session)


@router.get("/pending", response_model=ChargesResponse)
@read_limit
async def list_pending_charges(request: Request, session: AsyncSession = Depends(get_db)):
    return await _received_charges(request, PaymentRequestStatus.PENDING, session)


def created_item(charge: PaymentRequestModel, payer: UserModel) -> CreatedPaymentRequestResponseSchema:
    return CreatedPaymentRequestResponseSchema(
        id=charge.id, group_id=charge.group_id, payer_alias=payer.alias,
        masked_name=mask_full_name(payer.full_name), amount=charge.amount,
        percentage=float(charge.percentage) if charge.percentage is not None else None,
        concept=charge.concept, status=charge.status.value,
        created_at=charge.created_at, updated_at=charge.updated_at,
    )


@router.get("/created", response_model=CreatedPaymentRequestsSchema)
@read_limit
async def list_created_charges(request: Request, limit: int = Query(50, ge=1, le=100),
                               offset: int = Query(0, ge=0),
                               session: AsyncSession = Depends(get_db)):
    creator_id = await current_user_id(request)
    if isinstance(creator_id, JSONResponse):
        return creator_id
    actor = await session.get(UserModel, creator_id)
    if actor is None or not actor.is_active or actor.role != UserRole.USER:
        return api_error(403, "FORBIDDEN", "Esta vista es exclusiva para usuarios activos")
    requester_account, payer_account = aliased(AccountModel), aliased(AccountModel)
    payer = aliased(UserModel)
    rows = (await session.execute(
        select(PaymentRequestModel, payer)
        .join(requester_account, requester_account.id == PaymentRequestModel.requester_account_id)
        .join(payer_account, payer_account.id == PaymentRequestModel.payer_account_id)
        .join(payer, payer.id == payer_account.user_id)
        .where(requester_account.user_id == creator_id, requester_account.type == AccountType.USER_WALLET)
        .order_by(PaymentRequestModel.created_at.desc(), PaymentRequestModel.id.desc())
        .offset(offset).limit(limit + 1)
    )).all()
    return CreatedPaymentRequestsSchema(
        items=[created_item(charge, user) for charge, user in rows[:limit]],
        next_offset=offset + limit if len(rows) > limit else None,
    )


@router.post("/group", response_model=GroupPaymentRequestResponseSchema, status_code=201,
             dependencies=[Depends(financial_key_header)])
@limiter.limit("15/minute", key_func=lookup_rate_key)
async def create_group(request: Request, payload: CreateGroupPaymentRequestSchema,
                       session: AsyncSession = Depends(get_db)):
    creator_id = await current_user_id(request)
    if isinstance(creator_id, JSONResponse):
        return creator_id
    try:
        async with session.begin():
            group_id, rows = await create_group_charge(
                session, creator_id, payload.total_amount, payload.concept,
                [RequestedRecipient(row.recipient_alias, row.percentage, row.is_locked)
                 for row in payload.recipients],
            )
            response = GroupPaymentRequestResponseSchema(
                group_id=group_id, total_amount=payload.total_amount,
                items=[created_item(charge, payer) for charge, payer in rows],
            )
    except GroupChargeError as exc:
        status = 401 if exc.code == "UNAUTHORIZED" else 404 if exc.code in {"PAYER_NOT_FOUND", "ACCOUNT_NOT_FOUND"} else 422
        return api_error(status, exc.code, str(exc))
    return response


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
        if requester is None or not requester.is_active or requester.role != UserRole.USER:
            return api_error(401, "UNAUTHORIZED", "Token inválido")
        payer = (await session.execute(select(UserModel).where(
            UserModel.alias_blind_index == blind_index(alias, "users.alias"), UserModel.is_active.is_(True),
            UserModel.role == UserRole.USER))).scalar_one_or_none()
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


@router.post("/{charge_id}/pay", response_model=PaidResponse,
             dependencies=[Depends(financial_key_header)])
@limiter.limit("15/minute", key_func=lookup_rate_key)
async def pay_charge(request: Request, charge_id: uuid.UUID,
                     session: AsyncSession = Depends(get_db)):
    payer_id = await current_user_id(request)
    if isinstance(payer_id, JSONResponse):
        return payer_id
    try:
        async with session.begin():
            actor = await session.get(UserModel, payer_id)
            if actor is None or not actor.is_active or actor.role != UserRole.USER:
                return api_error(401, "UNAUTHORIZED", "Token inválido")
            outcome = await process_charge_payment(session, charge_id, payer_id,
                                                   "TRF-" + uuid.uuid4().hex)
            if isinstance(outcome, InsufficientChargePayment):
                response = JSONResponse(status_code=400, content={
                    "code": "INSUFFICIENT_FUNDS_FOR_PAYMENT_REQUEST",
                    "message": f"Requieres {outcome.required_amount:,} COP incluyendo GMF de {outcome.gmf_tax:,} COP. Tu cobro se mantendrá pendiente.",
                    "details": {"current_balance": outcome.current_balance,
                                "required_amount": outcome.required_amount, "gmf_tax": outcome.gmf_tax,
                                "shortfall": max(0, outcome.required_amount - outcome.current_balance),
                                "charge_status": "PENDING"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            else:
                paid_charge = await session.get(PaymentRequestModel, charge_id)
                response = PaidResponse(charge_id=charge_id, status="COMPLETED",
                                        amount=paid_charge.amount, gmf_tax=outcome.gmf_tax,
                                        total_debit=paid_charge.amount + outcome.gmf_tax,
                                        transaction_reference=outcome.reference_id,
                                        paid_at=outcome.created_at)
    except TaxAccountConfigurationException:
        return api_error(503, "GMF_NOT_CONFIGURED", "Cuenta colectora GMF no configurada")
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
            if actor is None or not actor.is_active or actor.role != UserRole.USER:
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
            if actor is None or not actor.is_active or actor.role != UserRole.USER:
                return api_error(401, "UNAUTHORIZED", "Token inválido")
            charge = await cancel_charge(session, charge_id, requester_id)
            response = TransitionResponse(charge_id=charge.id, status=charge.status.value)
    except (ChargeNotFoundException, ChargeForbiddenException, ChargeStateConflictException) as exc:
        return charge_error(exc)
    return response
