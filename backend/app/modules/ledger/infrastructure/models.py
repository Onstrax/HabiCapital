"""PostgreSQL persistence models; never import these into the pure domain layer."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, ForeignKey, Index, SmallInteger,
    String, Enum as SQLEnum, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from app.core.field_encryption import EncryptedJSON, EncryptedText, blind_index


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"


class AccountType(str, enum.Enum):
    USER_WALLET = "USER_WALLET"
    SYSTEM_OMNIBUS = "SYSTEM_OMNIBUS"


class TransactionType(str, enum.Enum):
    TOPUP = "TOPUP"
    P2P_TRANSFER = "P2P_TRANSFER"
    PAYMENT_REQUEST_PAYMENT = "PAYMENT_REQUEST_PAYMENT"


class TransactionStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class PaymentRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class IdempotencyStatus(str, enum.Enum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


def pg_enum(enum_type: type[enum.Enum], name: str) -> SQLEnum:
    return SQLEnum(enum_type, name=name, native_enum=True)


def primary_uuid() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
                         server_default=text("gen_random_uuid()"))


def created_timestamp() -> Mapped[datetime]:
    return mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class UserModel(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("alias_blind_index ~ '^[0-9a-f]{64}$'", name="chk_alias_blind_index"),)

    id: Mapped[uuid.UUID] = primary_uuid()
    email: Mapped[str] = mapped_column(EncryptedText("users.email"), nullable=False)
    email_blind_index: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False,
        default=lambda context: blind_index(context.get_current_parameters()["email"]))
    alias: Mapped[str] = mapped_column(EncryptedText("users.alias"), nullable=False)
    alias_blind_index: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False,
        default=lambda context: blind_index(context.get_current_parameters()["alias"], "users.alias"))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(EncryptedText("users.full_name"), nullable=False)
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"), nullable=False,
                                         default=UserRole.USER, server_default=text("'USER'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True,
                                            server_default=text("true"))
    created_at: Mapped[datetime] = created_timestamp()
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False,
                                                  server_default=func.now(), onupdate=func.now())
    account: Mapped["AccountModel | None"] = relationship(back_populates="user", uselist=False)


class AccountModel(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = primary_uuid()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
                                               unique=True, nullable=False)
    account_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    type: Mapped[AccountType] = mapped_column(pg_enum(AccountType, "account_type"), nullable=False,
                                             default=AccountType.USER_WALLET, server_default=text("'USER_WALLET'"))
    created_at: Mapped[datetime] = created_timestamp()
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False,
                                                  server_default=func.now(), onupdate=func.now())
    user: Mapped[UserModel] = relationship(back_populates="account")


class TransactionModel(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = primary_uuid()
    reference_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    type: Mapped[TransactionType] = mapped_column(pg_enum(TransactionType, "transaction_type"), nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(pg_enum(TransactionStatus, "transaction_status"), nullable=False)
    concept: Mapped[str] = mapped_column(EncryptedText("transactions.concept"), nullable=False)
    created_at: Mapped[datetime] = created_timestamp()


class LedgerEntryModel(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_positive_amount"),
        CheckConstraint("debit_account_id <> credit_account_id", name="chk_different_accounts"),
        Index("idx_ledger_debit_acc", "debit_account_id"),
        Index("idx_ledger_credit_acc", "credit_account_id"),
        Index("idx_ledger_created_at", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = primary_uuid()
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=False)
    debit_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    credit_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = created_timestamp()


class PaymentRequestModel(Base):
    __tablename__ = "payment_requests"
    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_pr_positive_amount"),
        CheckConstraint("requester_account_id <> payer_account_id", name="chk_pr_different_accounts"),
        Index("idx_payment_requests_payer_status", "payer_account_id", "status"),
        Index("idx_payment_requests_requester_status", "requester_account_id", "status"),
    )

    id: Mapped[uuid.UUID] = primary_uuid()
    requester_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    payer_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    concept: Mapped[str] = mapped_column(EncryptedText("payment_requests.concept"), nullable=False)
    status: Mapped[PaymentRequestStatus] = mapped_column(pg_enum(PaymentRequestStatus, "payment_request_status"), nullable=False,
                                                        default=PaymentRequestStatus.PENDING, server_default=text("'PENDING'"))
    created_at: Mapped[datetime] = created_timestamp()
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False,
                                                  server_default=func.now(), onupdate=func.now())


class IdempotencyRecordModel(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (Index("idx_idempotency_expires", "expires_at"),)

    key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[IdempotencyStatus] = mapped_column(pg_enum(IdempotencyStatus, "idempotency_status"), nullable=False,
                                                     default=IdempotencyStatus.PROCESSING, server_default=text("'PROCESSING'"))
    response_code: Mapped[int | None] = mapped_column(SmallInteger)
    response_body: Mapped[dict | None] = mapped_column(EncryptedJSON("idempotency_records.response_body"))
    created_at: Mapped[datetime] = created_timestamp()
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = primary_uuid()
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(EncryptedJSON("audit_logs.payload"), nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(EncryptedText("audit_logs.ip_address"))
    created_at: Mapped[datetime] = created_timestamp()
