"""Additive provider lifecycle; preserve all applied deterministic message receipts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='0030_conversational_chat'
down_revision='0029_assistant_messages'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('chat_generations',sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('actor_id',sa.Uuid(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('store_id',sa.Uuid(),sa.ForeignKey('stores.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('run_id',sa.Uuid(),sa.ForeignKey('planning_runs.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('key_digest',sa.String(64),nullable=False),sa.Column('request_digest',sa.String(64),nullable=False),
        sa.Column('record_digest',sa.String(64),nullable=False),sa.Column('status',sa.String(16),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('record_json',JSONB(none_as_null=True),nullable=False),
        sa.UniqueConstraint('actor_id','store_id','run_id','key_digest',name='uq_chat_generation_key'),
        sa.CheckConstraint("status IN ('running','completed','failed')",name='ck_chat_generation_status'),
        sa.CheckConstraint("jsonb_typeof(record_json)='object'",name='ck_chat_generation_record'))
    op.execute("""CREATE FUNCTION retain_chat_generation() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Chat evidence cannot be deleted'; END IF;
        IF OLD.status<>'running' OR NEW.status='running' OR
           (NEW.id,NEW.actor_id,NEW.store_id,NEW.run_id,NEW.key_digest,NEW.request_digest,NEW.created_at) IS DISTINCT FROM
           (OLD.id,OLD.actor_id,OLD.store_id,OLD.run_id,OLD.key_digest,OLD.request_digest,OLD.created_at) OR
           (NEW.record_json - ARRAY['status','finished_at','result','output','error_code']) IS DISTINCT FROM
           (OLD.record_json - ARRAY['status','finished_at','result','output','error_code'])
        THEN RAISE EXCEPTION 'Invalid chat transition'; END IF; RETURN NEW;
      END $$""")
    op.execute('CREATE TRIGGER retain_chat_generation BEFORE UPDATE OR DELETE ON chat_generations FOR EACH ROW EXECUTE FUNCTION retain_chat_generation()')


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM chat_generations) THEN
        RAISE EXCEPTION 'Retained chat generations prevent downgrade'; END IF; END $$""")
    op.drop_table('chat_generations');op.execute('DROP FUNCTION retain_chat_generation()')
