"""Durable summary generations, no PlanningRun/data backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0028_assistant_summaries'
down_revision = '0027_self_service_stores'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('plan_summary_generations',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('actor_id',sa.Uuid(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('store_id',sa.Uuid(),sa.ForeignKey('stores.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('run_id',sa.Uuid(),sa.ForeignKey('planning_runs.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('identity_digest',sa.String(64),nullable=False),
        sa.Column('record_digest',sa.String(64),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('record_json',JSONB(none_as_null=True),nullable=False),
        sa.CheckConstraint("status IN ('running','completed','failed')",name='ck_plan_summary_status'),
        sa.CheckConstraint("jsonb_typeof(record_json)='object'",name='ck_plan_summary_record'))
    op.create_index('uq_plan_summary_identity','plan_summary_generations',
        ['actor_id','store_id','run_id','identity_digest'],unique=True,postgresql_where=sa.text("status <> 'failed'"))
    op.create_table('plan_summary_receipts',
        sa.Column('actor_id',sa.Uuid(),sa.ForeignKey('users.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('store_id',sa.Uuid(),sa.ForeignKey('stores.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('run_id',sa.Uuid(),sa.ForeignKey('planning_runs.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('key_digest',sa.String(64),primary_key=True),
        sa.Column('request_digest',sa.String(64),nullable=False),
        sa.Column('generation_id',sa.Uuid(),sa.ForeignKey('plan_summary_generations.id',ondelete='RESTRICT'),nullable=False))
    op.execute("""CREATE FUNCTION retain_plan_summary() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Summary evidence cannot be deleted'; END IF;
        IF TG_TABLE_NAME='plan_summary_receipts' THEN RAISE EXCEPTION 'Summary receipts are immutable'; END IF;
        IF OLD.status<>'running' OR NEW.status='running' OR
           (NEW.id,NEW.actor_id,NEW.store_id,NEW.run_id,NEW.identity_digest,NEW.created_at) IS DISTINCT FROM
           (OLD.id,OLD.actor_id,OLD.store_id,OLD.run_id,OLD.identity_digest,OLD.created_at) OR
           (NEW.record_json - ARRAY['status','finished_at','result','error_code']) IS DISTINCT FROM
           (OLD.record_json - ARRAY['status','finished_at','result','error_code'])
        THEN RAISE EXCEPTION 'Invalid summary transition'; END IF;
        RETURN NEW;
      END $$""")
    for table in ('plan_summary_generations','plan_summary_receipts'):
        op.execute(f'CREATE TRIGGER retain_plan_summary BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION retain_plan_summary()')


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM plan_summary_generations) THEN
        RAISE EXCEPTION 'Retained summaries prevent downgrade'; END IF; END $$""")
    op.drop_table('plan_summary_receipts')
    op.drop_table('plan_summary_generations')
    op.execute('DROP FUNCTION retain_plan_summary()')
