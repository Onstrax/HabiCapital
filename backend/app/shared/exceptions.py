"""Business errors shared between use cases and HTTP adapters."""


class InsufficientFundsException(Exception):
    def __init__(self, current_balance: int, required_amount: int):
        self.current_balance = current_balance
        self.required_amount = required_amount
        super().__init__("Saldo insuficiente para completar la transferencia")


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


class OmnibusConfigurationException(Exception):
    pass
