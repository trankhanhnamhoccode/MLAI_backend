"""B3 additive declined terminal; Import owns revisions 0019 and 0021."""
from alembic import op
import sqlalchemy as sa

revision = "0022_invitation_decline"
down_revision = "0020_password_reset_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("staff_invitations", sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint("ck_staff_invitations_status", "staff_invitations", type_="check")
    op.create_check_constraint("ck_staff_invitations_status", "staff_invitations",
        "status IN ('pending','accepted','revoked','expired','declined')")


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM staff_invitations WHERE status='declined' OR declined_at IS NOT NULL)
         OR EXISTS (SELECT 1 FROM invitation_events WHERE record_json->>'kind'='DECLINED')
         OR EXISTS (SELECT 1 FROM staff_request_receipts WHERE operation LIKE '%/decline') THEN
        RAISE EXCEPTION 'B3 decline evidence requires retention before downgrade';
      END IF;
    END $$""")
    op.drop_constraint("ck_staff_invitations_status", "staff_invitations", type_="check")
    op.create_check_constraint("ck_staff_invitations_status", "staff_invitations",
        "status IN ('pending','accepted','revoked','expired')")
    op.drop_column("staff_invitations", "declined_at")
