"""Reject invalid financial commands before touching persistence."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.ledger.infrastructure.models import UserRole
from app.modules.ledger.use_cases.admin_topup import execute_admin_topup
from app.modules.ledger.use_cases.transfer_money import execute_p2p_transfer_transactional
from app.modules.payment_requests.use_cases.charges import create_charge_request
from app.shared.exceptions import SelfTransferForbiddenException

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("amount", [True, 0, -1, 1.5, 2**63])
async def test_transfer_rejects_amounts_outside_positive_bigint(amount):
    session = AsyncMock()
    with pytest.raises(ValueError):
        await execute_p2p_transfer_transactional(session, uuid.uuid4(), uuid.uuid4(),
                                                 amount, "concept", "ref")
    session.execute.assert_not_awaited()


async def test_transfer_rejects_self_transfer():
    with pytest.raises(SelfTransferForbiddenException):
        await execute_p2p_transfer_transactional(AsyncMock(), uuid.UUID(int=1), uuid.UUID(int=1),
                                                 1, "self", "ref")


@pytest.mark.parametrize("concept", ["  ", "x" * 256])
async def test_transfer_rejects_invalid_concept(concept):
    with pytest.raises(ValueError):
        await execute_p2p_transfer_transactional(AsyncMock(), uuid.UUID(int=1), uuid.UUID(int=2),
                                                 1, concept, "ref")


@pytest.mark.parametrize("amount", [True, 0, -1, 1.25, 2**63])
async def test_charge_creation_rejects_invalid_amounts(amount):
    session = AsyncMock()
    with pytest.raises(ValueError):
        await create_charge_request(session, uuid.uuid4(), uuid.uuid4(), amount, "concept")
    session.add.assert_not_called()


async def test_charge_creation_rejects_same_account_and_invalid_concept():
    account_id = uuid.uuid4()
    with pytest.raises(ValueError):
        await create_charge_request(AsyncMock(), account_id, account_id, 1, "concept")
    for concept in ("", " " * 3, "x" * 256):
        with pytest.raises(ValueError):
            await create_charge_request(AsyncMock(), uuid.uuid4(), uuid.uuid4(), 1, concept)


@pytest.mark.parametrize("amount,concept", [(0, "valid"), (1, " "), (1, "x" * 256)])
async def test_topup_validates_amount_and_concept_before_session_access(amount, concept):
    session = AsyncMock()
    with pytest.raises(ValueError):
        await execute_admin_topup(session, uuid.uuid4(), uuid.uuid4(), amount, concept, "ref")
    session.get.assert_not_awaited()


async def test_topup_refuses_non_admin_even_if_the_call_reaches_the_use_case():
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(is_active=True, role=UserRole.USER)
    with pytest.raises(PermissionError):
        await execute_admin_topup(session, uuid.uuid4(), uuid.uuid4(), 1, "valid", "ref")
    session.execute.assert_not_awaited()
