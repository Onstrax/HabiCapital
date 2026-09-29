"""Shared OpenAPI inputs for authentication and financial idempotency."""

from fastapi import Header
from fastapi.security import HTTPBearer


bearer_auth = HTTPBearer(auto_error=False, description="JWT obtenido en /api/v1/auth/login")


def financial_key_header(
    key: str = Header(alias="X-Idempotency-Key"),
) -> None:
    """Expose the middleware-required header in OpenAPI; middleware validates it."""
