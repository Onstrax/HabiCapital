"""Persistent, user scoped claim and response replay for mutating HTTP requests."""

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Request, Response
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.core.database import get_session_factory
from app.core.security import decode_access_token
from app.modules.ledger.infrastructure.models import IdempotencyRecordModel, IdempotencyStatus

MUTATIVE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
PUBLIC_PATHS = {"/api/v1/auth/login", "/api/v1/auth/register"}
FINANCIAL_PATHS = {"/api/v1/admin/topup", "/api/v1/transfers/execute"}


def error(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"code": code, "message": message, "details": {},
                         "timestamp": datetime.now(timezone.utc).isoformat()}, status_code=status_code)


class DatabaseIdempotencyStore:
    """A unique PostgreSQL key serializes claims across workers and instances."""

    async def claim(self, key: uuid.UUID, user_id: uuid.UUID, request_hash: str):
        async with get_session_factory()() as session:
            async with session.begin():
                statement = (
                    insert(IdempotencyRecordModel)
                    .values(key=key, user_id=user_id, request_hash=request_hash,
                            status=IdempotencyStatus.PROCESSING,
                            expires_at=datetime.now(timezone.utc) + timedelta(hours=24))
                    .on_conflict_do_nothing(index_elements=[IdempotencyRecordModel.key])
                    .returning(IdempotencyRecordModel.key)
                )
                created = (await session.execute(statement)).scalar_one_or_none()
                if created is not None:
                    return None
                return (await session.execute(select(IdempotencyRecordModel).where(
                    IdempotencyRecordModel.key == key))).scalar_one()

    async def complete(self, key: uuid.UUID, response_code: int, response_body: Any):
        async with get_session_factory()() as session:
            async with session.begin():
                result = await session.execute(
                    update(IdempotencyRecordModel)
                    .where(IdempotencyRecordModel.key == key,
                           IdempotencyRecordModel.status == IdempotencyStatus.PROCESSING)
                    .values(status=IdempotencyStatus.COMPLETED, response_code=response_code,
                            response_body=response_body)
                )
                if result.rowcount != 1:
                    raise RuntimeError("Idempotency claim was lost")

    async def fail(self, key: uuid.UUID):
        async with get_session_factory()() as session:
            async with session.begin():
                await session.execute(update(IdempotencyRecordModel)
                                      .where(IdempotencyRecordModel.key == key,
                                             IdempotencyRecordModel.status == IdempotencyStatus.PROCESSING)
                                      .values(status=IdempotencyStatus.FAILED))


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, store=None, settings: Settings | None = None):
        super().__init__(app)
        self.store = store or DatabaseIdempotencyStore()
        self.settings = settings

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in MUTATIVE_METHODS or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        path = request.url.path
        required = path in FINANCIAL_PATHS or (path.startswith("/api/v1/charges/") and path.endswith("/pay"))
        raw_key = request.headers.get("X-Idempotency-Key")
        if not raw_key:
            if required:
                return error("IDEMPOTENCY_KEY_REQUIRED", "Falta X-Idempotency-Key", 400)
            return await call_next(request)

        try:
            key = uuid.UUID(raw_key)
            if key.version != 4 or str(key) != raw_key.lower():
                raise ValueError("The key must be a canonical UUIDv4")
        except ValueError:
            return error("INVALID_IDEMPOTENCY_KEY", "X-Idempotency-Key debe ser UUIDv4", 400)

        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return error("UNAUTHORIZED", "Token requerido", 401)
        try:
            claims = decode_access_token(authorization.removeprefix("Bearer "),
                                         settings=self.settings or get_settings())
        except jwt.InvalidTokenError:
            return error("UNAUTHORIZED", "Token inválido", 401)
        user_id = uuid.UUID(claims["sub"])
        request.state.user_id = user_id
        payload = await request.body()
        if len(payload) > 1_048_576:
            return error("PAYLOAD_TOO_LARGE", "Payload demasiado grande", 413)
        request_hash = hashlib.sha256(request.method.encode() + b":" + path.encode() + b":" + payload).hexdigest()

        record = await self.store.claim(key, user_id, request_hash)
        if record is not None:
            if record.user_id != user_id:
                return error("IDEMPOTENCY_KEY_CONFLICT", "La llave pertenece a otra identidad", 409)
            if record.request_hash != request_hash:
                return error("IDEMPOTENCY_PAYLOAD_MISMATCH", "La llave ya se usó con otro payload", 422)
            if record.status == IdempotencyStatus.COMPLETED:
                return JSONResponse(record.response_body, status_code=record.response_code,
                                    headers={"X-Cache": "HIT-IDEMPOTENCY"})
            return error("IDEMPOTENCY_IN_PROGRESS", "La solicitud ya está en proceso o requiere conciliación", 409)

        try:
            response = await call_next(request)
            if not 200 <= response.status_code < 300:
                await self.store.fail(key)
                return response
            content = b"".join([chunk async for chunk in response.body_iterator])
            response_body = json.loads(content) if content else None
            await self.store.complete(key, response.status_code, response_body)
            headers = dict(response.headers)
            headers.pop("content-length", None)
            return Response(content=content, status_code=response.status_code,
                            headers=headers, media_type="application/json")
        except Exception:
            # Never release a claim after a possible financial commit. A retry
            # stays blocked until an operator reconciles the persisted result.
            raise
