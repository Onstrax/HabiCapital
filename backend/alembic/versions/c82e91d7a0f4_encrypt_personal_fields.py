"""Encrypt existing personal fields and replace email equality with a blind index.

Revision ID: c82e91d7a0f4
Revises: b71f9ab4c832

Requires the two independent PII keys before running. This migration is atomic;
it does not alter posted ledger entries. Downgrade is deliberately unsupported.
"""

import json

import sqlalchemy as sa
from alembic import op

from app.core.field_encryption import blind_index, encrypt_text, validate_pii_keys

revision = "c82e91d7a0f4"
down_revision = "b71f9ab4c832"
branch_labels = None
depends_on = None


def upgrade() -> None:
    validate_pii_keys()
    conn = op.get_bind()
    op.add_column("users", sa.Column("email_blind_index", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("alias_blind_index", sa.String(64), nullable=True))
    op.drop_constraint("chk_alias_format", "users", type_="check")
    for table, column in (("users", "email"), ("users", "full_name"),
                          ("users", "alias"), ("transactions", "concept"),
                          ("payment_requests", "concept"), ("audit_logs", "ip_address")):
        length = 150 if column == "full_name" else 20 if column == "alias" else 45 if column == "ip_address" else 255
        op.alter_column(table, column, existing_type=sa.String(length),
                        type_=sa.Text(), existing_nullable=column == "ip_address")

    # The previous trigger prohibits changing even a pending charge's concept.
    # Alembic's transaction holds the table lock until the encrypted backfill commits.
    op.execute("DROP TRIGGER trg_protect_charge_state ON payment_requests")
    for row in conn.execute(sa.text("SELECT id, email, alias, full_name FROM users")).mappings():
        conn.execute(sa.text("""UPDATE users SET email=:email, alias=:alias,
                            full_name=:full_name, email_blind_index=:email_blind_index,
                            alias_blind_index=:alias_blind_index WHERE id=:id"""), {
            "id": row["id"], "email": encrypt_text(row["email"], "users.email"),
            "alias": encrypt_text(row["alias"], "users.alias"),
            "full_name": encrypt_text(row["full_name"], "users.full_name"),
            "email_blind_index": blind_index(row["email"]),
            "alias_blind_index": blind_index(row["alias"], "users.alias"),
        })
    for table, purpose in (("transactions", "transactions.concept"),
                           ("payment_requests", "payment_requests.concept")):
        for row in conn.execute(sa.text(f"SELECT id, concept FROM {table}")).mappings():
            conn.execute(sa.text(f"UPDATE {table} SET concept=:concept WHERE id=:id"), {
                "id": row["id"], "concept": encrypt_text(row["concept"], purpose),
            })
    op.execute("""CREATE TRIGGER trg_protect_charge_state BEFORE UPDATE ON payment_requests
                  FOR EACH ROW EXECUTE FUNCTION protect_charge_state()""")
    for row in conn.execute(sa.text("SELECT id, ip_address FROM audit_logs WHERE ip_address IS NOT NULL")).mappings():
        conn.execute(sa.text("UPDATE audit_logs SET ip_address=:value WHERE id=:id"), {
            "id": row["id"], "value": encrypt_text(row["ip_address"], "audit_logs.ip_address")})

    for table, purpose, column, where in (
        ("audit_logs", "audit_logs.payload", "payload", ""),
        ("idempotency_records", "idempotency_records.response_body", "response_body",
         "WHERE response_body IS NOT NULL"),
    ):
        primary = "id" if table == "audit_logs" else "key"
        for row in conn.execute(sa.text(
            f"SELECT {primary}, {column} FROM {table} {where}")).mappings():
            wrapped = {"__encrypted_v1__": encrypt_text(
                json.dumps(row[column], ensure_ascii=False, separators=(",", ":")), purpose)}
            conn.execute(sa.text(f"UPDATE {table} SET {column}=CAST(:value AS jsonb) "
                                 f"WHERE {primary}=:pk"),
                         {"pk": row[primary], "value": json.dumps(wrapped)})
    op.alter_column("audit_logs", "payload", server_default=None,
                    existing_type=sa.dialects.postgresql.JSONB(), existing_nullable=False)
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_alias", table_name="users")
    op.alter_column("users", "email_blind_index", nullable=False,
                    existing_type=sa.String(64))
    op.alter_column("users", "alias_blind_index", nullable=False,
                    existing_type=sa.String(64))
    op.create_index("ix_users_email_blind_index", "users", ["email_blind_index"], unique=True)
    op.create_index("ix_users_alias_blind_index", "users", ["alias_blind_index"], unique=True)
    op.create_check_constraint("chk_alias_blind_index", "users",
                               "alias_blind_index ~ '^[0-9a-f]{64}$'")


def downgrade() -> None:
    raise RuntimeError("No se permite volver a columnas PII en texto plano")
