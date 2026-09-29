"""Argon2id password hashing and short lived HS256 access tokens."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import Settings, get_settings


pw_context = CryptContext(
    schemes=["argon2"],
    argon2__type="ID",
    argon2__memory_cost=65536,
    argon2__time_cost=3,
    argon2__parallelism=4,
)
DUMMY_PASSWORD_HASH = pw_context.hash("invalid-account-placeholder")


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("A nonempty password is required")
    return pw_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pw_context.verify(plain_password, hashed_password)
    except (TypeError, ValueError):
        return False


def create_access_token(data: dict[str, Any], *, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if "sub" not in data:
        raise ValueError("Missing required access token claims")
    uuid.UUID(str(data["sub"]))
    now = datetime.now(timezone.utc)
    claims = {"sub": str(data["sub"])}
    claims.update(iat=now, nbf=now,
                  exp=now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str, *, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    claims = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"],
                        options={"require": ["sub", "exp", "iat", "nbf"]})
    try:
        uuid.UUID(claims["sub"])
    except (ValueError, TypeError, KeyError) as exc:
        raise jwt.InvalidTokenError("Invalid identity claims") from exc
    return claims
