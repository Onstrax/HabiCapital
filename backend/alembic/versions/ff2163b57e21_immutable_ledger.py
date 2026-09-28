"""Prevent updates, deletes, and truncation of posted ledger entries.

Revision ID: ff2163b57e21
Revises: 07f45e204cec
"""

from alembic import op

revision = "ff2163b57e21"
down_revision = "07f45e204cec"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION reject_ledger_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'ledger_entries is immutable' USING ERRCODE = '55000';
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_ledger_entries_no_update_delete
        BEFORE UPDATE OR DELETE ON ledger_entries FOR EACH ROW
        EXECUTE FUNCTION reject_ledger_mutation();
    """)
    op.execute("""
        CREATE TRIGGER trg_ledger_entries_no_truncate
        BEFORE TRUNCATE ON ledger_entries FOR EACH STATEMENT
        EXECUTE FUNCTION reject_ledger_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_ledger_entries_no_truncate ON ledger_entries")
    op.execute("DROP TRIGGER trg_ledger_entries_no_update_delete ON ledger_entries")
    op.execute("DROP FUNCTION reject_ledger_mutation()")
