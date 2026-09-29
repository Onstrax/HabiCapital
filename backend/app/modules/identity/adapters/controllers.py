"""Versioned HTTP contracts for registration, login, and recipient lookup."""

import hashlib
import uuid
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.openapi_security import bearer_auth
from app.core.security import DUMMY_PASSWORD_HASH, create_access_token, decode_access_token, hash_password, verify_password
from app.modules.identity.infrastructure.repository import SqlIdentityRepository
from app.modules.identity.use_cases.identity import (
    IdentityRepository, authenticate_user, lookup_recipient, register_user,
)
from app.shared.utils.security_utils import sanitize_alias


def lookup_rate_key(request: Request) -> str:
    token = request.headers.get("Authorization", "")
    return f"{get_remote_address(request)}:{hashlib.sha256(token.encode()).hexdigest()}"


limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/api/v1")


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)


class RegisterRequest(StrictSchema):
    email: EmailStr
    alias: str
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=2, max_length=150)

    @field_validator("alias")
    @classmethod
    def valid_alias(cls, value: str) -> str:
        return sanitize_alias(value)


class RegisterResponse(StrictSchema):
    id: uuid.UUID
    email: EmailStr
    alias: str
    full_name: str
    role: str
    created_at: datetime


class LoginRequest(StrictSchema):
    email: EmailStr
    password: str


class LoginResponse(StrictSchema):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 900


class LookupRequest(StrictSchema):
    recipient_alias: str

    @field_validator("recipient_alias")
    @classmethod
    def valid_alias(cls, value: str) -> str:
        return sanitize_alias(value)


class LookupResponse(StrictSchema):
    recipient_id: uuid.UUID
    recipient_alias: str
    masked_name: str


def get_identity_repository(session: AsyncSession = Depends(get_db)) -> IdentityRepository:
    return SqlIdentityRepository(session)


def api_error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={
        "code": code, "message": message, "details": {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@router.post("/auth/register", response_model=RegisterResponse, status_code=201)
async def register(payload: RegisterRequest, repo: IdentityRepository = Depends(get_identity_repository)):
    try:
        user = await register_user(repo, str(payload.email), payload.alias,
                                   payload.password, payload.full_name, hash_password)
    except IntegrityError:
        return api_error(409, "IDENTITY_CONFLICT", "Correo o alias no disponible")
    return RegisterResponse(id=user.id, email=user.email, alias=user.alias,
                            full_name=user.full_name, role=user.role, created_at=user.created_at)


@router.post("/auth/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login(request: Request, payload: LoginRequest, repo: IdentityRepository = Depends(get_identity_repository)):
    user = await authenticate_user(repo, str(payload.email), payload.password,
                                   verify_password, DUMMY_PASSWORD_HASH)
    if not user:
        return api_error(401, "INVALID_CREDENTIALS", "Credenciales inválidas")
    token = create_access_token({"sub": str(user.id), "email": user.email,
                                 "alias": user.alias, "role": user.role})
    return LoginResponse(access_token=token, expires_in=get_settings().ACCESS_TOKEN_EXPIRE_MINUTES * 60)


async def current_user_id(request: Request) -> uuid.UUID | JSONResponse:
    value = request.headers.get("Authorization", "")
    if not value.startswith("Bearer "):
        return api_error(401, "UNAUTHORIZED", "Token requerido")
    try:
        claims = decode_access_token(value.removeprefix("Bearer "))
    except jwt.InvalidTokenError:
        return api_error(401, "UNAUTHORIZED", "Token inválido")
    return uuid.UUID(claims["sub"])


@router.post("/transfers/lookup", response_model=LookupResponse,
             dependencies=[Depends(bearer_auth)])
@limiter.limit("10/minute", key_func=lookup_rate_key)
async def lookup(request: Request, payload: LookupRequest,
                 repo: IdentityRepository = Depends(get_identity_repository)):
    user_id = await current_user_id(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    actor = await repo.find_by_id(user_id)
    if not actor or not actor.is_active:
        return api_error(401, "UNAUTHORIZED", "Token inválido")
    found = await lookup_recipient(repo, payload.recipient_alias)
    if not found:
        return api_error(404, "RECIPIENT_NOT_FOUND", "El alias no corresponde a un usuario activo")
    user, masked_name = found
    return LookupResponse(recipient_id=user.id, recipient_alias=user.alias,
                          masked_name=masked_name)
