"""All split calculations use integer COP and hundredths of a percent."""

import uuid

import pytest

from app.modules.payment_requests.domain.split_calculator import (
    RecipientAllocation, calculate_exact_cop_split, redistribute_percentages,
)


def recipients(*values):
    return [RecipientAllocation(uuid.uuid4(), percentage, locked) for percentage, locked in values]


def test_three_way_split_preserves_every_peso():
    items = recipients((33.33, False), (33.33, False), (33.34, False))
    result = calculate_exact_cop_split(100_000, items)
    assert [amount for _, amount, _ in result] == [33330, 33330, 33340]
    assert sum(amount for _, amount, _ in result) == 100_000
    assert all(isinstance(amount, int) for _, amount, _ in result)


def test_locked_half_redistributes_only_unlocked_recipients():
    items = recipients((50, True), (25, False), (25, False))
    assert redistribute_percentages(items) == [50.0, 25.0, 25.0]
    assert sum(amount for _, amount, _ in calculate_exact_cop_split(100_000, items)) == 100_000


def test_manual_change_preserves_locked_half_and_redistributes_rest():
    items = recipients((50, True), (30, False), (25, False))
    adjusted = redistribute_percentages(items, edited_index=1)
    assert adjusted == [50.0, 30.0, 20.0]


def test_non_divisible_pesos_go_to_last_unlocked_row():
    items = recipients((33.33, True), (33.33, False), (33.34, False))
    assert [amount for _, amount, _ in calculate_exact_cop_split(101, items)] == [33, 33, 35]


@pytest.mark.parametrize("total, shares", [
    (1, [(50, False), (50, False)]),
    (100, [(60, True), (30, False)]),
    (100, [(33.33, True), (33.33, True), (33.34, True)]),
    (2**63, [(100, False)]),
])
def test_invalid_or_unallocatable_split_is_rejected(total, shares):
    with pytest.raises(ValueError):
        calculate_exact_cop_split(total, recipients(*shares))


def test_precision_and_duplicate_ids_are_rejected():
    recipient = uuid.uuid4()
    with pytest.raises(ValueError):
        calculate_exact_cop_split(100, [RecipientAllocation(recipient, 50.001, False),
                                        RecipientAllocation(uuid.uuid4(), 49.999, False)])
    with pytest.raises(ValueError):
        calculate_exact_cop_split(100, [RecipientAllocation(recipient, 50, False),
                                        RecipientAllocation(recipient, 50, False)])
