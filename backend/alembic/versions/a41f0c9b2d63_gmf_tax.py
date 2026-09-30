"""GMF collector and persisted transaction fee; historical entries stay untouched."""
import os
import uuid
import sqlalchemy as sa
from alembic import op

revision = "a41f0c9b2d63"
down_revision = "9c321bb4e817"
branch_labels = None
depends_on = None

def upgrade():
    # PostgreSQL requires commit before a newly added enum value can be used.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE account_type ADD VALUE IF NOT EXISTS 'SYSTEM_TAX_GMF'")
    op.alter_column("accounts", "user_id", existing_type=sa.UUID(), nullable=True)
    op.create_check_constraint("chk_account_owner", "accounts",
        "(type = 'SYSTEM_TAX_GMF' AND user_id IS NULL) OR "
        "(type <> 'SYSTEM_TAX_GMF' AND user_id IS NOT NULL)")
    op.create_index("uq_system_tax_gmf", "accounts", ["type"], unique=True,
                    postgresql_where=sa.text("type = 'SYSTEM_TAX_GMF'"))
    op.add_column("transactions", sa.Column("gmf_tax", sa.BigInteger(), nullable=False, server_default="0"))
    op.create_check_constraint("chk_transaction_gmf", "transactions", "gmf_tax >= 0")
    collector_id = uuid.UUID(os.getenv("SYSTEM_TAX_GMF_ACCOUNT_ID", "00000000-0000-4000-8000-000000000004"))
    op.get_bind().execute(sa.text(
        "INSERT INTO accounts (id, user_id, account_number, type) "
        "VALUES (:id, NULL, 'SYSTEM-TAX-GMF', 'SYSTEM_TAX_GMF')"), {"id": collector_id})

def downgrade():
    if op.get_bind().execute(sa.text(
        "SELECT EXISTS(SELECT 1 FROM transactions WHERE gmf_tax > 0) OR "
        "EXISTS(SELECT 1 FROM ledger_entries l JOIN accounts a ON "
        "a.id IN (l.debit_account_id, l.credit_account_id) WHERE a.type = 'SYSTEM_TAX_GMF')"
    )).scalar():
        raise RuntimeError("No se puede retirar GMF con asientos históricos")
    op.execute("DELETE FROM accounts WHERE type = 'SYSTEM_TAX_GMF'")
    op.drop_constraint("chk_transaction_gmf", "transactions", type_="check")
    op.drop_column("transactions", "gmf_tax")
    op.drop_index("uq_system_tax_gmf", table_name="accounts")
    op.drop_constraint("chk_account_owner", "accounts", type_="check")
    op.alter_column("accounts", "user_id", existing_type=sa.UUID(), nullable=False)
    # PostgreSQL enum value is intentionally retained; deleting it is unsafe.
