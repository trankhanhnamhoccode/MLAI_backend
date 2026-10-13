"""B2 private delivery for canonical RESET tokens; 0019 reserved for Import."""
from alembic import op
import sqlalchemy as sa

revision = "0020_password_reset_delivery"
down_revision = "0018_email_verification"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("password_reset_deliveries",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("token_digest", sa.String(64), sa.ForeignKey("credential_tokens.digest", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("proof_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("claim", sa.UUID()),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_code", sa.String(40)),
        sa.CheckConstraint("status IN ('queued','delivered','failed') AND attempts >= 0 AND proof_revision >= 1", name="ck_password_reset_delivery_status"))
    op.create_index("ix_password_reset_deliveries_expires_at", "password_reset_deliveries", ["expires_at"])


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM password_reset_deliveries) THEN
        RAISE EXCEPTION 'B2 evidence requires retention before downgrade';
      END IF;
    END $$""")
    op.drop_table("password_reset_deliveries")
