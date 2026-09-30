"""Real PostgreSQL financial invariants, including fees and retries."""
import uuid
import pytest
from sqlalchemy import select, func
from app.core.config import get_settings
from app.core.security import create_access_token
from app.modules.ledger.domain.services import calculate_account_balance
from app.modules.ledger.infrastructure.models import (
    AccountModel, AccountType, LedgerEntryModel, TransactionModel, TransactionStatus,
    TransactionType, UserModel, UserRole, PaymentRequestModel, PaymentRequestStatus,
)

async def seed(sessions, balance=100400):
    async with sessions() as s, s.begin():
        a = UserModel(email="gmfa@test.example", alias="gmf_a", full_name="Gmf A", password_hash="hash")
        b = UserModel(email="gmfb@test.example", alias="gmf_b", full_name="Gmf B", password_hash="hash")
        admin = UserModel(email="gmfadmin@test.example", alias="gmf_admin", full_name="Admin",
                          password_hash="hash", role=UserRole.ADMIN)
        s.add_all([a,b,admin])
        await s.flush()
        aa = AccountModel(user_id=a.id, account_number=uuid.uuid4().hex[:20])
        bb = AccountModel(user_id=b.id, account_number=uuid.uuid4().hex[:20])
        oo = AccountModel(user_id=admin.id, account_number=uuid.uuid4().hex[:20], type=AccountType.SYSTEM_OMNIBUS)
        s.add_all([aa,bb,oo])
        await s.flush()
        tx = TransactionModel(reference_id=str(uuid.uuid4()), type=TransactionType.TOPUP,
                              status=TransactionStatus.SUCCESS, concept="Seed")
        s.add(tx)
        await s.flush()
        s.add(LedgerEntryModel(transaction_id=tx.id, debit_account_id=oo.id, credit_account_id=aa.id, amount=balance))
    return a,b,admin,aa,bb,oo

def auth(user, key=None):
    return {"Authorization": "Bearer " + create_access_token({"sub":str(user.id)}),
            "X-Idempotency-Key": key or str(uuid.uuid4())}

@pytest.mark.asyncio
async def test_p2p_exact_fee_and_idempotent_replay(async_client, sessions):
    a,b,_,aa,bb,_ = await seed(sessions)
    headers = auth(a)
    payload = {"recipient_id":str(b.id), "amount":100000, "concept":"GMF transfer"}
    first = await async_client.post("/api/v1/transfers/execute", json=payload, headers=headers)
    second = await async_client.post("/api/v1/transfers/execute", json=payload, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["gmf_tax"] == 400 and first.json()["total_debit"] == 100400
    assert second.headers["X-Cache"] == "HIT-IDEMPOTENCY"
    async with sessions() as s:
        tax_id = get_settings().SYSTEM_TAX_GMF_ACCOUNT_ID
        assert await calculate_account_balance(aa.id,s) == 0
        assert await calculate_account_balance(bb.id,s) == 100000
        assert await calculate_account_balance(tax_id,s) == 400
        assert await s.scalar(select(func.count()).select_from(LedgerEntryModel)) == 3
    history = await async_client.get("/api/v1/ledger/movements", headers=auth(a))
    transfer = next(x for x in history.json()["items"] if x["type"] == "P2P_TRANSFER")
    assert transfer["amount"] == 100000 and transfer["gmf_tax"] == 400 and transfer["total_debit"] == 100400
    assert len(history.json()["items"]) == 2  # funding + one logical transfer, no duplicate fee row

@pytest.mark.asyncio
async def test_global_balance_after_multiple_taxed_transfers(async_client,sessions):
    a,b,_,aa,bb,oo = await seed(sessions, 200000)
    for amount in (100000,100,999):
        response = await async_client.post("/api/v1/transfers/execute",
            json={"recipient_id":str(b.id),"amount":amount,"concept":"Audit"},headers=auth(a))
        assert response.status_code == 201
    async with sessions() as s:
        tax = await calculate_account_balance(get_settings().SYSTEM_TAX_GMF_ACCOUNT_ID,s)
        assert tax == 404
        balances = [await calculate_account_balance(x,s) for x in (aa.id,bb.id,oo.id,get_settings().SYSTEM_TAX_GMF_ACCOUNT_ID)]
        assert sum(balances) == 0
        rows = (await s.execute(select(LedgerEntryModel))).scalars().all()
        assert sum(x.amount for x in rows if x.debit_account_id) == sum(x.amount for x in rows if x.credit_account_id)

@pytest.mark.asyncio
async def test_exact_principal_without_fee_rejected_atomically(async_client,sessions):
    a,b,_,aa,bb,_ = await seed(sessions,100000)
    response = await async_client.post("/api/v1/transfers/execute",
        json={"recipient_id":str(b.id),"amount":100000,"concept":"Cannot pay fee"},headers=auth(a))
    assert response.status_code == 400 and response.json()["code"] == "INSUFFICIENT_FUNDS"
    assert response.json()["details"]["required_amount"] == 100400
    assert response.json()["details"]["shortfall"] == response.json()["details"]["gmf_tax"] == 400
    async with sessions() as s:
        assert await calculate_account_balance(aa.id,s) == 100000
        assert await calculate_account_balance(bb.id,s) == 0
        assert await s.scalar(select(func.count()).select_from(TransactionModel)) == 1
        assert await s.scalar(select(func.count()).select_from(LedgerEntryModel)) == 1

@pytest.mark.asyncio
async def test_admin_topup_exempt(async_client,sessions):
    a,_,admin,aa,_,_ = await seed(sessions,100000)
    r = await async_client.post("/api/v1/admin/topup",
        json={"target_user_alias":a.alias,"amount":100000,"concept":"Exempt"},headers=auth(admin))
    assert r.status_code == 200
    async with sessions() as s:
        assert await calculate_account_balance(aa.id,s) == 200000
        assert await calculate_account_balance(get_settings().SYSTEM_TAX_GMF_ACCOUNT_ID,s) == 0
        assert await s.scalar(select(func.count()).select_from(LedgerEntryModel)) == 2

@pytest.mark.asyncio
@pytest.mark.parametrize("funded",[True,False])
async def test_payment_request_charges_fee_or_remains_pending(async_client,sessions,funded):
    a,b,_,aa,bb,_ = await seed(sessions,100400 if funded else 100000)
    async with sessions() as s,s.begin():
        charge = PaymentRequestModel(requester_account_id=bb.id,payer_account_id=aa.id,
                                    amount=100000,concept="Charge",status=PaymentRequestStatus.PENDING)
        s.add(charge)
        await s.flush()
        cid=charge.id
    r = await async_client.post(f"/api/v1/charges/{cid}/pay",headers=auth(a))
    assert r.status_code == (200 if funded else 400)
    if funded:
        assert r.json()["gmf_tax"] == 400 and r.json()["total_debit"] == 100400
    else:
        assert r.json()["code"] == "INSUFFICIENT_FUNDS_FOR_PAYMENT_REQUEST"
        assert r.json()["details"]["required_amount"] == 100400
    async with sessions() as s:
        assert (await s.get(PaymentRequestModel,cid)).status == (
            PaymentRequestStatus.COMPLETED if funded else PaymentRequestStatus.PENDING)
        assert await calculate_account_balance(get_settings().SYSTEM_TAX_GMF_ACCOUNT_ID,s) == (400 if funded else 0)

@pytest.mark.asyncio
async def test_lookup_optional_amount_breakdown(async_client,sessions):
    a,b,*_=await seed(sessions)
    r=await async_client.post("/api/v1/transfers/lookup",json={"recipient_alias":b.alias,"amount":100000},headers=auth(a))
    assert r.status_code == 200 and r.json()["gmf_tax"] == 400 and r.json()["total_debit"] == 100400
    r=await async_client.post("/api/v1/transfers/lookup",json={"recipient_alias":b.alias},headers=auth(a))
    assert r.status_code == 200 and r.json()["amount"] is None

@pytest.mark.asyncio
async def test_missing_collector_fails_closed_and_overflow_is_rejected(async_client,sessions):
    a,b,_,aa,_,_=await seed(sessions)
    r=await async_client.post("/api/v1/transfers/execute",
        json={"recipient_id":str(b.id),"amount":2**63-1,"concept":"Overflow"},headers=auth(a))
    assert r.status_code == 400 and r.json()["code"] == "BALANCE_LIMIT_EXCEEDED"
    lookup=await async_client.post("/api/v1/transfers/lookup",
        json={"recipient_alias":b.alias,"amount":2**63-1},headers=auth(a))
    assert lookup.status_code == 422
    async with sessions() as s,s.begin():
        await s.delete(await s.get(AccountModel,get_settings().SYSTEM_TAX_GMF_ACCOUNT_ID))
    r=await async_client.post("/api/v1/transfers/execute",
        json={"recipient_id":str(b.id),"amount":1,"concept":"No collector"},headers=auth(a))
    assert r.status_code == 503 and r.json()["code"] == "GMF_NOT_CONFIGURED"
    async with sessions() as s:
        assert await calculate_account_balance(aa.id,s) == 100400
        assert await s.scalar(select(func.count()).select_from(LedgerEntryModel)) == 1

@pytest.mark.asyncio
async def test_collector_overflow_posts_nothing(async_client,sessions):
    a,b,_,aa,_,oo=await seed(sessions)
    async with sessions() as s,s.begin():
        tx=TransactionModel(reference_id=str(uuid.uuid4()),type=TransactionType.TOPUP,
                            status=TransactionStatus.SUCCESS,concept="Collector bound")
        s.add(tx)
        await s.flush()
        s.add(LedgerEntryModel(transaction_id=tx.id,debit_account_id=oo.id,
            credit_account_id=get_settings().SYSTEM_TAX_GMF_ACCOUNT_ID,amount=2**63-1))
    r=await async_client.post("/api/v1/transfers/execute",
        json={"recipient_id":str(b.id),"amount":1,"concept":"Fee overflow"},headers=auth(a))
    assert r.status_code == 400 and r.json()["code"] == "BALANCE_LIMIT_EXCEEDED"
    async with sessions() as s:
        assert await calculate_account_balance(aa.id,s) == 100400
        assert await s.scalar(select(func.count()).select_from(LedgerEntryModel)) == 2

@pytest.mark.asyncio
async def test_cancel_and_reject_never_collect_tax(async_client,sessions):
    a,b,*_=await seed(sessions)
    for action,actor in [("cancel",b),("reject",a)]:
        created=await async_client.post("/api/v1/charges",
            json={"payer_alias":a.alias,"amount":100000,"concept":"Exempt transition"},headers=auth(b))
        r=await async_client.post(f"/api/v1/charges/{created.json()['id']}/{action}",headers=auth(actor))
        assert r.status_code == 200
    async with sessions() as s:
        assert await calculate_account_balance(get_settings().SYSTEM_TAX_GMF_ACCOUNT_ID,s) == 0
        assert await s.scalar(select(func.count()).select_from(LedgerEntryModel)) == 1
