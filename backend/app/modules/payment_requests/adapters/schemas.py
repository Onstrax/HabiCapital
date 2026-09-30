"""Strict HTTP contracts for group and outbound payment requests."""

import uuid
from datetime import datetime

from pydantic import Field, field_validator, computed_field
from app.modules.ledger.domain.gmf_calculator import calculate_gmf_tax

from app.modules.identity.adapters.controllers import StrictSchema
from app.modules.payment_requests.domain.split_calculator import percentage_points
from app.shared.utils.security_utils import sanitize_alias


class RecipientSplitItem(StrictSchema):
    recipient_alias: str
    percentage: float
    is_locked: bool

    @field_validator("recipient_alias")
    @classmethod
    def valid_alias(cls, value: str) -> str:
        return sanitize_alias(value)

    @field_validator("percentage")
    @classmethod
    def valid_percentage(cls, value: float) -> float:
        if percentage_points(value) <= 0:
            raise ValueError("El porcentaje debe ser positivo")
        return value


class CreateGroupPaymentRequestSchema(StrictSchema):
    total_amount: int = Field(gt=0, le=2**63 - 1)
    concept: str = Field(min_length=1, max_length=255)
    recipients: list[RecipientSplitItem] = Field(min_length=1, max_length=100)

    @field_validator("recipients")
    @classmethod
    def valid_recipients(cls, value: list[RecipientSplitItem]) -> list[RecipientSplitItem]:
        aliases = [row.recipient_alias for row in value]
        if len(set(aliases)) != len(aliases):
            raise ValueError("No se permiten aliases duplicados")
        if sum(percentage_points(row.percentage) for row in value) != 10_000:
            raise ValueError("La suma debe ser 100.00%")
        return value


class CreatedPaymentRequestResponseSchema(StrictSchema):
    id: uuid.UUID
    group_id: uuid.UUID | None
    payer_alias: str
    masked_name: str
    amount: int
    percentage: float | None
    concept: str
    status: str
    created_at: datetime
    updated_at: datetime


    @computed_field
    @property
    def gmf_tax(self) -> int:
        return calculate_gmf_tax(self.amount)

    @computed_field
    @property
    def total_debit(self) -> int:
        return self.amount + self.gmf_tax


class GroupPaymentRequestResponseSchema(StrictSchema):
    group_id: uuid.UUID
    total_amount: int
    items: list[CreatedPaymentRequestResponseSchema]


class CreatedPaymentRequestsSchema(StrictSchema):
    items: list[CreatedPaymentRequestResponseSchema]
    next_offset: int | None = None
