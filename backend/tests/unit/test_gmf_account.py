"""Provisioning refuses collisions instead of reassigning existing accounts."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.ledger.infrastructure import gmf_account
from app.modules.ledger.infrastructure.models import AccountType
from app.core.config import DEFAULT_SYSTEM_TAX_GMF_ACCOUNT_ID as TAX
from app.shared.exceptions import TaxAccountConfigurationException

@pytest.mark.asyncio
@pytest.mark.parametrize("existing,collision", [
    ([],False), ([],True),
    ([SimpleNamespace(id=TAX,user_id=None)],False),
    ([SimpleNamespace(id=uuid.uuid4(),user_id=None)],False),
])
async def test_safe_provisioning(monkeypatch,existing,collision):
    monkeypatch.setattr(gmf_account,"get_settings",lambda:SimpleNamespace(SYSTEM_TAX_GMF_ACCOUNT_ID=TAX))
    s=AsyncMock(spec=AsyncSession)
    result=Mock()
    result.scalars.return_value.all.return_value=existing
    s.execute.return_value=result
    s.get.return_value=object() if collision else None
    if collision or (existing and existing[0].id != TAX):
        with pytest.raises(TaxAccountConfigurationException):
            await gmf_account.ensure_gmf_account(s)
        s.add.assert_not_called()
    else:
        account=await gmf_account.ensure_gmf_account(s)
        assert account.id == TAX
        if not existing:
            assert account.user_id is None and account.type == AccountType.SYSTEM_TAX_GMF
            s.add.assert_called_once()
