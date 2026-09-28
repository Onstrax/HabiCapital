import uuid
from unittest.mock import AsyncMock, Mock

import jwt
import pytest

from app.core.config import Settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.shared.utils.security_utils import mask_full_name, sanitize_alias
from app.modules.identity.use_cases.identity import authenticate_user


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        DATABASE_URL="postgresql+psycopg://test:test@localhost/test",
        JWT_SECRET_KEY="s" * 64,
        ADMIN_PASSWORD="test-password-123",
    )


def test_argon2id_round_trip_and_parameters():
    encoded = hash_password("StrongPassword123!")
    assert encoded.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert verify_password("StrongPassword123!", encoded)
    assert not verify_password("wrong", encoded)
    assert hash_password("StrongPassword123!") != encoded


def test_jwt_claims_expiration_signature_and_algorithm(settings):
    user_id = str(uuid.uuid4())
    claims = {"sub": user_id, "email": "a@example.test", "role": "USER", "alias": "user_a"}
    token = create_access_token(claims, settings=settings)
    decoded = decode_access_token(token, settings=settings)
    assert all(decoded[k] == v for k, v in claims.items())
    assert decoded["exp"] - decoded["iat"] == 15 * 60
    assert decoded["nbf"] == decoded["iat"]
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token + "tampered", settings=settings)
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(jwt.encode({**claims, "iat": 1, "nbf": 1, "exp": 2},
                                       settings.JWT_SECRET_KEY, algorithm="HS256"), settings=settings)


@pytest.mark.parametrize("name,masked", [
    ("Juan Esteban Gómez", "J*** E****** G****"),
    ("  Ana   María  Pérez  ", "A** M**** P****"),
    ("Álvaro", "Á*****"),
    ("A B", "A* B*"),
    ("", ""),
])
def test_mask_full_name(name, masked):
    assert mask_full_name(name) == masked


def test_alias_normalization_and_validation():
    assert sanitize_alias("  JUAN_123  ") == "juan_123"
    for alias in ("a", "a-b", "éste", "user name", "x" * 21):
        with pytest.raises(ValueError):
            sanitize_alias(alias)


@pytest.mark.asyncio
async def test_unknown_email_still_performs_password_verification():
    repo = AsyncMock()
    repo.find_by_email.return_value = None
    verify = Mock(return_value=False)
    result = await authenticate_user(repo, "missing@example.com", "attempt", verify, "dummy-hash")
    assert result is None
    verify.assert_called_once_with("attempt", "dummy-hash")
