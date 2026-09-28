"""Enforce one omnibus account and immutable terminal charge states.

Revision ID: b71f9ab4c832
Revises: ff2163b57e21
"""

from alembic import op

revision = "b71f9ab4c832"
down_revision = "ff2163b57e21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE UNIQUE INDEX ux_single_system_omnibus
        ON accounts (type) WHERE type = 'SYSTEM_OMNIBUS';
    """)
    op.execute("""
        CREATE FUNCTION protect_charge_state() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
                RAISE EXCEPTION 'payment request cannot be removed' USING ERRCODE = '55000';
            END IF;
            IF OLD.status <> 'PENDING' THEN
                RAISE EXCEPTION 'terminal payment request is immutable' USING ERRCODE = '55000';
            END IF;
            IF NEW.requester_account_id <> OLD.requester_account_id
                OR NEW.payer_account_id <> OLD.payer_account_id
                OR NEW.amount <> OLD.amount OR NEW.concept <> OLD.concept
                OR NEW.created_at <> OLD.created_at
                OR NEW.status NOT IN ('PENDING', 'COMPLETED', 'REJECTED', 'CANCELLED') THEN
                RAISE EXCEPTION 'invalid payment request mutation' USING ERRCODE = '55000';
            END IF;
            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_protect_charge_state BEFORE UPDATE ON payment_requests
        FOR EACH ROW EXECUTE FUNCTION protect_charge_state();
    """)
    op.execute("""
        CREATE TRIGGER trg_protect_charge_delete BEFORE DELETE ON payment_requests
        FOR EACH ROW EXECUTE FUNCTION protect_charge_state();
    """)
    op.execute("""
        CREATE TRIGGER trg_protect_charge_truncate BEFORE TRUNCATE ON payment_requests
        FOR EACH STATEMENT EXECUTE FUNCTION protect_charge_state();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_protect_charge_truncate ON payment_requests")
    op.execute("DROP TRIGGER trg_protect_charge_delete ON payment_requests")
    op.execute("DROP TRIGGER trg_protect_charge_state ON payment_requests")
    op.execute("DROP FUNCTION protect_charge_state()")
    op.execute("DROP INDEX ux_single_system_omnibus")
