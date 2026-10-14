"""Retain self-service Store creation receipts; no seeded authority or facts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision='0027_self_service_stores'
down_revision='0026_collaboration_requests'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('store_creation_receipts',
        sa.Column('actor_id',sa.Uuid(),sa.ForeignKey('users.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('key_digest',sa.String(64),primary_key=True),
        sa.Column('request_digest',sa.String(64),nullable=False),
        sa.Column('store_id',sa.Uuid(),sa.ForeignKey('stores.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('result',JSONB(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('store_id',name='uq_store_creation_store'),
        sa.CheckConstraint("jsonb_typeof(result)='object'",name='ck_store_creation_result'))
    op.execute("""CREATE FUNCTION retain_store_creation_receipt() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Store creation receipts are immutable'; END $$""")
    op.execute('CREATE TRIGGER retain_store_creation_receipt BEFORE UPDATE OR DELETE ON store_creation_receipts FOR EACH ROW EXECUTE FUNCTION retain_store_creation_receipt()')


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM store_creation_receipts) THEN
        RAISE EXCEPTION 'Retained Store creation receipts prevent downgrade'; END IF; END $$""")
    op.drop_table('store_creation_receipts')
    op.execute('DROP FUNCTION retain_store_creation_receipt()')
