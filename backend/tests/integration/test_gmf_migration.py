"""Upgrade an old encrypted schema without touching its immutable posted entries."""
import asyncio
import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text, select, func
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import get_settings, DEFAULT_SYSTEM_TAX_GMF_ACCOUNT_ID as TAX
from app.core.field_encryption import encrypt_text, blind_index
from app.modules.ledger.infrastructure.models import LedgerEntryModel
from app.modules.ledger.use_cases.transfer_money import execute_p2p_transfer_transactional

def test_upgrade_preserves_history_and_seeds_collector(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required")
    schema = "test_gmf_migration_" + uuid.uuid4().hex[:10]
    root = create_engine(url)
    with root.begin() as c:
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = make_url(url).update_query_dict({"options": "-csearch_path=" + schema})
    scoped_url = scoped.render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", scoped_url)
    monkeypatch.setenv("SYSTEM_TAX_GMF_ACCOUNT_ID",str(TAX))
    monkeypatch.setenv("JWT_SECRET_KEY", "t" * 64)
    monkeypatch.setenv("ADMIN_PASSWORD", "test-password-123")
    get_settings.cache_clear()
    cfg = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parents[2] / "alembic"))
    engine = create_engine(scoped)
    try:
        command.upgrade(cfg,"9c321bb4e817")
        users = [uuid.uuid4() for _ in range(3)]
        accounts = [uuid.uuid4() for _ in range(3)]
        txid, entryid = uuid.uuid4(),uuid.uuid4()
        with engine.begin() as c:
            for index, uid in enumerate(users):
                email,alias=f"old-{index}@test.example",f"old_{index}"
                c.execute(text("INSERT INTO users(id,email,alias,password_hash,full_name,email_blind_index,alias_blind_index) "
                               "VALUES (:id,:email,:alias,'hash',:name,:ei,:ai)"),
                    {"id":uid,"email":encrypt_text(email,"users.email"),"alias":encrypt_text(alias,"users.alias"),
                     "name":encrypt_text("Old User","users.full_name"),"ei":blind_index(email),
                     "ai":blind_index(alias,"users.alias")})
                c.execute(text("INSERT INTO accounts(id,user_id,account_number,type) VALUES(:id,:uid,:number,:kind)"),
                    {"id":accounts[index],"uid":uid,"number":f"OLD-{index}",
                     "kind":"SYSTEM_OMNIBUS" if index==2 else "USER_WALLET"})
            c.execute(text("INSERT INTO transactions(id,reference_id,type,status,concept) VALUES(:id,'OLD-TOPUP','TOPUP','SUCCESS',:concept)"),
                      {"id":txid,"concept":encrypt_text("Old","transactions.concept")})
            c.execute(text("INSERT INTO ledger_entries(id,transaction_id,debit_account_id,credit_account_id,amount) "
                           "VALUES(:id,:tx,:debit,:credit,1000)"),
                      {"id":entryid,"tx":txid,"debit":accounts[2],"credit":accounts[0]})
        command.upgrade(cfg,"head")
        with engine.connect() as c:
            assert c.execute(text("SELECT gmf_tax FROM transactions WHERE id=:id"),{"id":txid}).scalar_one()==0
            assert c.execute(text("SELECT amount FROM ledger_entries WHERE id=:id"),{"id":entryid}).scalar_one()==1000
            assert c.execute(text("SELECT type FROM accounts WHERE id=:id"),{"id":TAX}).scalar_one()=="SYSTEM_TAX_GMF"
        async def transfer():
            e=create_async_engine(scoped_url)
            try:
                factory=async_sessionmaker(e,expire_on_commit=False)
                async with factory() as s,s.begin():
                    tx=await execute_p2p_transfer_transactional(s,accounts[0],accounts[1],500,"New taxed","NEW-GMF")
                    assert tx.gmf_tax==2
                async with factory() as s:
                    assert await s.scalar(select(func.count()).select_from(LedgerEntryModel))==3
            finally:
                await e.dispose()
        asyncio.run(transfer())
        with pytest.raises(DBAPIError):
            with engine.begin() as c:
                c.execute(text("UPDATE ledger_entries SET amount=1 WHERE id=:id"),{"id":entryid})
        with pytest.raises(RuntimeError,match="históricos"):
            command.downgrade(cfg,"9c321bb4e817")
    finally:
        engine.dispose()
        with root.begin() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root.dispose()
        get_settings.cache_clear()
