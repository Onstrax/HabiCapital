"""The database sees ciphertext; resource mutations require the owning wallet."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import Text, cast, select

from app.core.field_encryption import blind_index
from app.core.security import create_access_token
from app.modules.ledger.infrastructure.models import (
    AccountModel, AuditLogModel, IdempotencyRecordModel, PaymentRequestModel,
    PaymentRequestStatus, TransactionModel, TransactionStatus, TransactionType,
    UserModel,
)


@pytest.mark.asyncio
async def test_private_fields_and_cached_responses_are_ciphertext(db_session):
    email = "private@example.test"
    user = UserModel(email=email, alias="private_user", full_name="Nombre Muy Privado",
                     password_hash="hash")
    db_session.add(user)
    await db_session.flush()
    transaction = TransactionModel(reference_id="PRIVATE-" + uuid.uuid4().hex,
                                   type=TransactionType.P2P_TRANSFER,
                                   status=TransactionStatus.SUCCESS, concept="Consulta médica privada")
    charge = PaymentRequestModel(requester_account_id=uuid.uuid4(), payer_account_id=uuid.uuid4(),
                                 amount=100, concept="Arriendo confidencial")
    audit = AuditLogModel(user_id=user.id, action="TEST", payload={"email": email})
    replay = IdempotencyRecordModel(key=uuid.uuid4(), user_id=user.id, request_hash="h" * 64,
                                    response_body={"concept": "Consulta médica privada"},
                                    expires_at=datetime.now(timezone.utc) + timedelta(hours=24))
    # Payment request FK rows must exist before inserting the charge.
    from app.modules.ledger.infrastructure.models import AccountType
    other = UserModel(email="other@example.test", alias="other_user", full_name="Otro Usuario",
                      password_hash="hash")
    db_session.add(other)
    await db_session.flush()
    first = AccountModel(user_id=user.id, account_number="ACC" + uuid.uuid4().hex[:17],
                         type=AccountType.USER_WALLET)
    second = AccountModel(user_id=other.id, account_number="ACC" + uuid.uuid4().hex[:17],
                          type=AccountType.USER_WALLET)
    db_session.add_all((first, second))
    await db_session.flush()
    charge.requester_account_id, charge.payer_account_id = first.id, second.id
    db_session.add_all((transaction, charge, audit, replay))
    await db_session.flush()
    row = (await db_session.execute(select(
        cast(UserModel.email, Text).label("email"),
        cast(UserModel.full_name, Text).label("full_name"),
        cast(UserModel.alias, Text).label("alias"),
        UserModel.email_blind_index, UserModel.alias_blind_index,
    ).where(UserModel.id == user.id))).one()
    assert row.email.startswith("enc:v1:") and email not in row.email
    assert row.full_name.startswith("enc:v1:") and "Nombre" not in row.full_name
    assert row.email_blind_index == blind_index(email)
    assert row.alias.startswith("enc:v1:") and "private_user" not in row.alias
    assert row.alias_blind_index == blind_index("private_user", "users.alias")
    assert user.email == email
    assert (await db_session.get(UserModel, user.id)).full_name == "Nombre Muy Privado"
    for model, pk, value in ((TransactionModel, transaction.id, "Consulta médica privada"),
                             (PaymentRequestModel, charge.id, "Arriendo confidencial")):
        cipher = await db_session.scalar(select(cast(model.concept, Text)).where(model.id == pk))
        assert cipher.startswith("enc:v1:") and value not in cipher
    assert "private@example.test" not in str(await db_session.scalar(
        select(cast(AuditLogModel.payload, Text)).where(AuditLogModel.id == audit.id)))
    assert "Consulta médica privada" not in str(await db_session.scalar(
        select(cast(IdempotencyRecordModel.response_body, Text)).where(IdempotencyRecordModel.key == replay.key)))


@pytest.mark.asyncio
async def test_only_payer_and_requester_can_change_a_pending_charge(sessions, async_client):
    async with sessions() as session, session.begin():
        users = [UserModel(email=f"owner-{uuid.uuid4()}@example.test", alias=f"owner_{i}",
                           full_name=f"Owner {i}", password_hash="hash") for i in range(3)]
        session.add_all(users)
        await session.flush()
        accounts = [AccountModel(user_id=user.id, account_number="ACC" + uuid.uuid4().hex[:17])
                    for user in users]
        session.add_all(accounts)
        await session.flush()
        charge = PaymentRequestModel(requester_account_id=accounts[0].id,
                                     payer_account_id=accounts[1].id, amount=500,
                                     concept="Almuerzo")
        session.add(charge)
        await session.flush()
        charge_id = charge.id
        outsider = users[2]
    token = create_access_token({"sub": str(outsider.id), "email": outsider.email,
                                 "role": "USER", "alias": outsider.alias})
    for action in ("pay", "reject", "cancel"):
        response = await async_client.post(f"/api/v1/charges/{charge_id}/{action}",
                                           headers={"Authorization": f"Bearer {token}",
                                                    "X-Idempotency-Key": str(uuid.uuid4())})
        assert response.status_code == 403
    async with sessions() as session:
        assert (await session.get(PaymentRequestModel, charge_id)).status == PaymentRequestStatus.PENDING
