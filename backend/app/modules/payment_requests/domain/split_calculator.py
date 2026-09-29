"""Pure split arithmetic: basis points for shares, BIGINT integers for COP."""

import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class RecipientAllocation:
    recipient_id: uuid.UUID
    percentage: float
    is_locked: bool


def percentage_points(value: float) -> int:
    """Return exact hundredths of a percent, rejecting excess precision."""
    try:
        percentage = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Porcentaje inválido") from None
    points = percentage * 100
    if not percentage.is_finite() or points != points.to_integral_value() or not 0 <= points <= 10_000:
        raise ValueError("El porcentaje requiere máximo dos decimales y rango 0–100")
    return int(points)


def redistribute_percentages(recipients: list[RecipientAllocation],
                             edited_index: int | None = None) -> list[float]:
    """Keep locked and just edited rows; spread the remainder across other unlocked rows."""
    if not recipients:
        raise ValueError("Se requiere al menos un destinatario")
    if edited_index is not None and not 0 <= edited_index < len(recipients):
        raise ValueError("Índice inválido")
    fixed = {index for index, row in enumerate(recipients) if row.is_locked}
    if edited_index is not None:
        fixed.add(edited_index)
    shares = [percentage_points(row.percentage) for row in recipients]
    remaining = 10_000 - sum(shares[index] for index in fixed)
    if remaining < 0:
        raise ValueError("Los porcentajes fijos exceden el 100%")
    free = [index for index in range(len(shares)) if index not in fixed]
    if not free and remaining:
        raise ValueError("No hay destinatario sin bloqueo para distribuir el saldo")
    if free:
        each, remainder = divmod(remaining, len(free))
        for index in free:
            shares[index] = each
        shares[free[-1]] += remainder
    return [share / 100 for share in shares]


def calculate_exact_cop_split(total_amount: int, recipients: list[RecipientAllocation]
                              ) -> list[tuple[uuid.UUID, int, float]]:
    if isinstance(total_amount, bool) or not isinstance(total_amount, int) or not 0 < total_amount <= 2**63 - 1:
        raise ValueError("El monto total debe ser COP positivo dentro de BIGINT")
    if not recipients or len({row.recipient_id for row in recipients}) != len(recipients):
        raise ValueError("Destinatarios ausentes o duplicados")
    points = [percentage_points(row.percentage) for row in recipients]
    if sum(points) != 10_000 or any(value <= 0 for value in points):
        raise ValueError("Los porcentajes deben sumar exactamente 100.00% y ser positivos")
    amounts = [total_amount * point // 10_000 for point in points]
    remainder = total_amount - sum(amounts)
    unlocked = [i for i, row in enumerate(recipients) if not row.is_locked]
    if remainder and not unlocked:
        raise ValueError("El residuo necesita un destinatario sin bloqueo")
    if remainder:
        amounts[unlocked[-1]] += remainder
    if any(amount <= 0 for amount in amounts):
        raise ValueError("Cada cobro debe tener al menos un peso")
    return [(row.recipient_id, amount, row.percentage) for row, amount in zip(recipients, amounts)]
