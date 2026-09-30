"""Exact COP GMF rule for this prototype; no floating-point monetary arithmetic."""

def calculate_gmf_tax(amount: int) -> int:
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise ValueError("El monto debe ser un entero COP")
    if amount <= 0:
        return 0
    return max(1, amount * 4 // 1000)
