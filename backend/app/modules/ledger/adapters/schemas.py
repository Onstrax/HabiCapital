"""Compatible lookup quote: absent amount means no monetary quote."""
import uuid
from pydantic import BaseModel, ConfigDict

class TransferLookupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    recipient_id: uuid.UUID
    recipient_alias: str
    alias: str
    masked_name: str
    amount: int | None = None
    gmf_tax: int | None = None
    total_debit: int | None = None
