"""Immutable chat receipts, no business state mutation or provider queue."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision='0029_assistant_messages'
down_revision='0028_assistant_summaries'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('assistant_messages',
        sa.Column('actor_id',sa.Uuid(),sa.ForeignKey('users.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('store_id',sa.Uuid(),sa.ForeignKey('stores.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('run_id',sa.Uuid(),sa.ForeignKey('planning_runs.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('key_digest',sa.String(64),primary_key=True),
        sa.Column('request_digest',sa.String(64),nullable=False),
        sa.Column('record_digest',sa.String(64),nullable=False),
        sa.Column('record_json',JSONB(none_as_null=True),nullable=False),
        sa.CheckConstraint("jsonb_typeof(record_json)='object'",name='ck_assistant_message_record'))
    op.execute("""CREATE FUNCTION retain_assistant_message() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Assistant messages are immutable'; END $$""")
    op.execute('CREATE TRIGGER retain_assistant_message BEFORE UPDATE OR DELETE ON assistant_messages FOR EACH ROW EXECUTE FUNCTION retain_assistant_message()')


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM assistant_messages) THEN
        RAISE EXCEPTION 'Retained messages prevent downgrade'; END IF; END $$""")
    op.drop_table('assistant_messages')
    op.execute('DROP FUNCTION retain_assistant_message()')
