"""Add immutable group identity and percentages to pending payment requests.

Revision ID: 9c321bb4e817
Revises: c82e91d7a0f4
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "9c321bb4e817"
down_revision = "c82e91d7a0f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payment_requests", sa.Column("group_id", UUID(as_uuid=True), nullable=True))
    op.add_column("payment_requests", sa.Column("percentage", sa.Numeric(5, 2), nullable=True))
    op.create_index("idx_payment_requests_group", "payment_requests", ["group_id"])
    op.create_check_constraint("chk_pr_group_percentage", "payment_requests",
                               "(group_id IS NULL AND percentage IS NULL) OR "
                               "(group_id IS NOT NULL AND percentage > 0 AND percentage <= 100)")
    op.execute("""
        CREATE OR REPLACE FUNCTION protect_charge_state() RETURNS trigger LANGUAGE plpgsql AS $$
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
                OR NEW.group_id IS DISTINCT FROM OLD.group_id
                OR NEW.percentage IS DISTINCT FROM OLD.percentage
                OR NEW.created_at <> OLD.created_at
                OR NEW.status NOT IN ('PENDING', 'COMPLETED', 'REJECTED', 'CANCELLED') THEN
                RAISE EXCEPTION 'invalid payment request mutation' USING ERRCODE = '55000';
            END IF;
            RETURN NEW;
        END;
        $$;
    """)


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM payment_requests WHERE group_id IS NOT NULL) ")).scalar():
        raise RuntimeError("No es seguro eliminar cobros grupales históricos")
    op.execute("""
        CREATE OR REPLACE FUNCTION protect_charge_state() RETURNS trigger LANGUAGE plpgsql AS $$
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
    op.drop_constraint("chk_pr_group_percentage", "payment_requests", type_="check")
    op.drop_index("idx_payment_requests_group", table_name="payment_requests")
    op.drop_column("payment_requests", "percentage")
    op.drop_column("payment_requests", "group_id")
