"""S410 purpose-specific durable PDF intent/job; history access index only."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision='0017_planning_exports'
down_revision='0016_planning_configuration'
branch_labels=depends_on=None


def upgrade():
    op.create_table('planning_exports',sa.Column('id',sa.UUID(),primary_key=True),
        sa.Column('job_id',sa.UUID(),nullable=False),
        sa.Column('run_id',sa.UUID(),sa.ForeignKey('planning_runs.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('store_id',sa.UUID(),sa.ForeignKey('stores.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('actor_id',sa.UUID(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('key_digest',sa.String(64),nullable=False),sa.Column('request_digest',sa.String(64),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),sa.Column('record_json',JSONB(none_as_null=True),nullable=False),
        sa.Column('record_digest',sa.String(64),nullable=False),
        sa.UniqueConstraint('job_id',name='uq_planning_export_job'),
        sa.UniqueConstraint('actor_id','store_id','run_id','key_digest',name='uq_planning_export_key'),
        sa.CheckConstraint("status IN ('queued','running','completed','failed')",name='ck_planning_export_status'),
        sa.CheckConstraint('revision>=1',name='ck_planning_export_revision'),
        sa.CheckConstraint("record_digest ~ '^[0-9a-f]{64}$' AND key_digest ~ '^[0-9a-f]{64}$' AND request_digest ~ '^[0-9a-f]{64}$'",name='ck_planning_export_digests'),
        sa.CheckConstraint("record_json->>'storage_version'='planning_export/1'",name='ck_planning_export_version'))
    op.create_index('ix_planning_exports_run_id','planning_exports',['run_id'])
    op.create_index('ix_planning_exports_store_id','planning_exports',['store_id'])
    op.create_index('ix_planning_exports_queue','planning_exports',['status','created_at','id'])
    op.create_index('ix_planning_runs_history','planning_runs',['store_id','accepted_at','id'])


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM planning_exports)')):
        raise RuntimeError('Refusing downgrade of retained PDF intents/artifact receipts')
    op.drop_index('ix_planning_runs_history',table_name='planning_runs')
    op.drop_table('planning_exports')
