"""B1 account email proof and private delivery; no ownership/grants backfill."""
from alembic import op
import sqlalchemy as sa

revision = "0018_email_verification"
down_revision = "0017_planning_exports"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("auth_accounts", sa.Column("proof_revision", sa.Integer(), nullable=False, server_default="1"))
    op.create_check_constraint("ck_auth_accounts_proof", "auth_accounts",
        "proof_revision >= 1 AND ((verified_at IS NULL AND verified_email IS NULL AND verification_reference IS NULL AND NOT credential_ready) OR (verified_at IS NOT NULL AND verified_email IS NOT NULL AND verification_reference IS NOT NULL))")
    for name, kind in (("verified_at", sa.DateTime(timezone=True)), ("verified_email", sa.String(320)), ("verification_reference", sa.String(1000))):
        op.alter_column("auth_accounts", name, existing_type=kind, nullable=True)
    op.create_table("email_verification_tokens",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("auth_accounts.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("proof_revision", sa.Integer(), nullable=False),
        sa.Column("credential_revision", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("purpose = 'EMAIL_VERIFY' AND proof_revision >= 1 AND credential_revision >= 1", name="ck_email_verification_binding"),
        sa.CheckConstraint("expires_at > issued_at", name="ck_email_verification_expiry"))
    op.create_index("ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"])
    op.create_table("email_verification_deliveries",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("token_digest", sa.String(64), sa.ForeignKey("email_verification_tokens.digest", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("claim", sa.UUID()),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_code", sa.String(40)),
        sa.CheckConstraint("status IN ('queued','delivered','failed') AND attempts >= 0", name="ck_email_verification_delivery_status"))
    op.create_index("ix_email_verification_deliveries_expires_at", "email_verification_deliveries", ["expires_at"])


def downgrade():
    # Transport and proof evidence is operational history, never disposable output.
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM email_verification_tokens)
         OR EXISTS (SELECT 1 FROM email_verification_deliveries)
         OR EXISTS (SELECT 1 FROM auth_accounts WHERE verified_at IS NULL) THEN
        RAISE EXCEPTION 'B1 evidence requires retention before downgrade';
      END IF;
    END $$""")
    op.drop_table("email_verification_deliveries")
    op.drop_table("email_verification_tokens")
    op.drop_constraint("ck_auth_accounts_proof", "auth_accounts", type_="check")
    for name, kind in (("verified_at", sa.DateTime(timezone=True)), ("verified_email", sa.String(320)), ("verification_reference", sa.String(1000))):
        op.alter_column("auth_accounts", name, existing_type=kind, nullable=False)
    op.drop_column("auth_accounts", "proof_revision")
