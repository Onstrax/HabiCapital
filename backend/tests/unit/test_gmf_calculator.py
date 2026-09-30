"""Red-first specification for exact integer COP taxation."""
import pytest
from app.modules.ledger.domain.gmf_calculator import calculate_gmf_tax

@pytest.mark.parametrize("amount,expected", [
    (100000, 400), (100, 1), (0, 0), (-1, 0), (249, 1), (250, 1),
    (500, 2), (999, 3), (2**63 - 1, ((2**63 - 1) * 4) // 1000),
])
def test_exact_integer_gmf(amount, expected):
    assert calculate_gmf_tax(amount) == expected

@pytest.mark.parametrize("amount", [True, 100.0, "100", None])
def test_rejects_non_integer_cop(amount):
    with pytest.raises(ValueError):
        calculate_gmf_tax(amount)
