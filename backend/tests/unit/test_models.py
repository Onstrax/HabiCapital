"""Schema contracts; PostgreSQL checks run when TEST_DATABASE_URL is supplied."""

import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import BigInteger, CheckConstraint, create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.modules.ledger.infrastructure.models import (
    AccountModel,
    AccountType,
    AuditLogModel,
    Base,
    IdempotencyRecordModel,
    LedgerEntryModel,
    PaymentRequestModel,
    TransactionModel,
    TransactionStatus,
    TransactionType,
    UserModel,
)


def test_all_models_are_mapped_and_monetary_amounts_are_bigint():
    models = (
        UserModel, AccountModel, TransactionModel, LedgerEntryModel,
        PaymentRequestModel, IdempotencyRecordModel, AuditLogModel,
    )
    assert {m.__tablename__ for m in models} <= set(Base.metadata.tables)
    for model in models:
        assert inspect(model).primary_key
    assert isinstance(LedgerEntryModel.__table__.c.amount.type, BigInteger)
    assert isinstance(PaymentRequestModel.__table__.c.amount.type, BigInteger)
    assert "balance" not in AccountModel.__table__.c


def test_models_can_be_instantiated():
    owner = uuid.uuid4()
    other = uuid.uuid4()
    tx = uuid.uuid4()
    user = UserModel(id=owner, email="owner@example.test", alias="owner", password_hash="hash", full_name="Owner")
    account = AccountModel(id=other, user_id=owner, account_number="ACC-1", type=AccountType.USER_WALLET)
    transaction = TransactionModel(id=tx, reference_id="REF-1", type=TransactionType.TOPUP,
                                   status=TransactionStatus.SUCCESS, concept="Test")
    entry = LedgerEntryModel(transaction_id=tx, debit_account_id=owner, credit_account_id=other, amount=1)
    request = PaymentRequestModel(requester_account_id=owner, payer_account_id=other, amount=1, concept="Test")
    record = IdempotencyRecordModel(key=uuid.uuid4(), user_id=owner, request_hash="a" * 64,
                                    expires_at=datetime.now(timezone.utc))
    audit = AuditLogModel(user_id=owner, action="TEST", payload={}, ip_address="127.0.0.1")
    assert (user.id, account.user_id, transaction.id, entry.amount, request.amount, record.user_id, audit.action) == (
        owner, owner, tx, 1, 1, owner, "TEST"
    )


def test_ledger_constraints_are_declared():
    constraints = {c.name: str(c.sqltext) for c in LedgerEntryModel.__table__.constraints
                   if isinstance(c, CheckConstraint)}
    assert constraints["chk_positive_amount"] == "amount > 0"
    assert constraints["chk_different_accounts"] == "debit_account_id <> credit_account_id"
    ddl = str(CreateTable(LedgerEntryModel.__table__).compile(dialect=postgresql.dialect()))
    assert "CHECK (amount > 0)" in ddl
    assert "CHECK (debit_account_id <> credit_account_id)" in ddl


@pytest.mark.parametrize("amount,same_account", [(-1, False), (0, False), (1, True)])
def test_database_rejects_invalid_ledger_entry(amount, same_account):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database for DB constraint tests")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS test_model_constraints")
        engine = engine.execution_options(schema_translate_map={None: "test_model_constraints"})
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            user_a = UserModel(email=f"a-{uuid.uuid4()}@example.test", alias=f"a{uuid.uuid4().hex[:12]}",
                               password_hash="hash", full_name="A")
            user_b = UserModel(email=f"b-{uuid.uuid4()}@example.test", alias=f"b{uuid.uuid4().hex[:12]}",
                               password_hash="hash", full_name="B")
            session.add_all((user_a, user_b))
            session.flush()
            a = AccountModel(user_id=user_a.id, account_number=uuid.uuid4().hex[:20])
            b = AccountModel(user_id=user_b.id, account_number=uuid.uuid4().hex[:20])
            tx = TransactionModel(reference_id=uuid.uuid4().hex, type=TransactionType.TOPUP,
                                  status=TransactionStatus.SUCCESS, concept="Test")
            session.add_all((a, b, tx))
            session.flush()
            session.add(LedgerEntryModel(transaction_id=tx.id, debit_account_id=a.id,
                                         credit_account_id=a.id if same_account else b.id, amount=amount))
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP SCHEMA IF EXISTS test_model_constraints CASCADE")
        engine.dispose()
