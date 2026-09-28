"""Identity policies and repository port; no web or ORM dependencies."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.shared.utils.security_utils import mask_full_name, sanitize_alias


@dataclass(frozen=True)
class Identity:
    id: uuid.UUID
    email: str
    alias: str
    full_name: str
    role: str
    is_active: bool
    password_hash: str
    created_at: datetime


class IdentityRepository(Protocol):
    async def register(self, email: str, alias: str, password_hash: str, full_name: str) -> Identity: ...
    async def find_by_email(self, email: str) -> Identity | None: ...
    async def find_by_alias(self, alias: str) -> Identity | None: ...
    async def find_by_id(self, user_id: uuid.UUID) -> Identity | None: ...


async def register_user(repo: IdentityRepository, email: str, alias: str,
                        password: str, full_name: str, hash_password) -> Identity:
    return await repo.register(email.strip().lower(), sanitize_alias(alias),
                               hash_password(password), full_name.strip())


async def authenticate_user(repo: IdentityRepository, email: str, password: str,
                            verify_password, dummy_password_hash: str) -> Identity | None:
    user = await repo.find_by_email(email.strip().lower())
    valid_password = verify_password(password, user.password_hash if user else dummy_password_hash)
    if user is None or not user.is_active or not valid_password:
        return None
    return user


async def lookup_recipient(repo: IdentityRepository, alias: str) -> tuple[Identity, str] | None:
    user = await repo.find_by_alias(sanitize_alias(alias))
    return (user, mask_full_name(user.full_name)) if user and user.is_active else None
