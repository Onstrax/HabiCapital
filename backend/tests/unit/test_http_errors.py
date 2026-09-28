"""Stable application-level validation and rate limit response contracts."""

import pytest

from app.main import rate_limit_error


@pytest.mark.asyncio
async def test_rate_limit_handler_returns_contract_error():
    response = await rate_limit_error(None, object())
    assert response.status_code == 429
    assert response.body and b'"code":"RATE_LIMIT_EXCEEDED"' in response.body
