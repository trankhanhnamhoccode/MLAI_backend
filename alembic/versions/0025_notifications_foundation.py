"""Add retained notification intents, projection and read receipts after integration."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0025_notifications_foundation"
down_revision = "0024_integrate_import_auth"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("notification_intents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id", ondelete="RESTRICT")),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload_version", sa.Integer(), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(64)), sa.Column("outcome", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "recipient_user_id", "event_type", name="uq_notification_identity"),
        sa.CheckConstraint("status IN ('pending','delivered','failed')", name="ck_notification_intent_status"),
        sa.CheckConstraint("attempt >= 0 AND payload_version = 1", name="ck_notification_intent_version"))
    op.create_index("ix_notification_due", "notification_intents", ["status", "next_attempt_at", "created_at"])
    op.create_table("notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("intent_id", sa.Uuid(), sa.ForeignKey("notification_intents.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("recipient_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id", ondelete="RESTRICT")),
        sa.Column("record", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)), sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_notification_revision"))
    op.create_index("ix_notifications_recipient_order", "notifications", ["recipient_user_id", "created_at", "id"])
    op.create_table("notification_read_receipts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("notification_id", sa.Uuid(), sa.ForeignKey("notifications.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("key_digest", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False), sa.Column("record", pg.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.String(200), nullable=False),
        sa.UniqueConstraint("actor_id", "notification_id", "key_digest", name="uq_notification_read_receipt"))
    op.execute("""
        CREATE FUNCTION protect_notification_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Notification evidence requires retention';
          END IF;
          IF TG_TABLE_NAME = 'notification_read_receipts' THEN
            RAISE EXCEPTION 'Notification read receipt is immutable';
          ELSIF TG_TABLE_NAME = 'notification_intents' THEN
            IF (to_jsonb(OLD) - ARRAY['status','attempt','next_attempt_at','error_code','outcome'])
                IS DISTINCT FROM (to_jsonb(NEW) - ARRAY['status','attempt','next_attempt_at','error_code','outcome']) THEN
              RAISE EXCEPTION 'Notification intent fact is immutable';
            END IF;
          ELSE
            IF (to_jsonb(OLD) - ARRAY['read_at','revision'])
                IS DISTINCT FROM (to_jsonb(NEW) - ARRAY['read_at','revision']) THEN
              RAISE EXCEPTION 'Notification content is immutable';
            END IF;
            IF OLD.read_at IS DISTINCT FROM NEW.read_at THEN
              IF NEW.revision <> OLD.revision + 1 THEN
                RAISE EXCEPTION 'Notification read revision must advance';
              END IF;
            ELSIF NEW.revision <> OLD.revision THEN
              RAISE EXCEPTION 'Notification no-op must retain revision';
            END IF;
          END IF;
          RETURN NEW;
        END $$
    """)
    for table in ("notification_intents", "notifications", "notification_read_receipts"):
        op.execute(f'CREATE TRIGGER protect_{table} BEFORE UPDATE OR DELETE ON {table} '
                   'FOR EACH ROW EXECUTE FUNCTION protect_notification_evidence()')


def downgrade():
    connection = op.get_bind()
    for table in ("notification_read_receipts", "notifications", "notification_intents"):
        if connection.scalar(sa.text(f'SELECT EXISTS(SELECT 1 FROM "{table}")')):
            raise RuntimeError("Notification retention prevents destructive downgrade; archive/review explicitly")
    for table in ("notification_read_receipts", "notifications", "notification_intents"):
        op.drop_table(table)
    op.execute("DROP FUNCTION protect_notification_evidence()")
