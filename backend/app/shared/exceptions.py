"""Business errors shared between use cases and HTTP adapters."""


class InsufficientFundsException(Exception):
    def __init__(self, current_balance: int, required_amount: int, gmf_tax: int = 0):
        self.current_balance = current_balance
        self.required_amount = required_amount
        self.gmf_tax = gmf_tax
        self.shortfall = max(0, required_amount - current_balance)
        super().__init__(f"Saldo insuficiente. Requieres {required_amount:,} COP "
                         f"incluyendo el 4x1000 ({gmf_tax:,} COP); faltan {self.shortfall:,} COP")


class AccountNotFoundException(Exception):
    pass


class BalanceLimitExceededException(Exception):
    pass


class SelfTransferForbiddenException(Exception):
    pass


class ChargeNotFoundException(Exception):
    pass


class ChargeStateConflictException(Exception):
    pass


class ChargeForbiddenException(Exception):
    pass


class TaxAccountConfigurationException(Exception):
    pass


class OmnibusConfigurationException(Exception):
    pass
