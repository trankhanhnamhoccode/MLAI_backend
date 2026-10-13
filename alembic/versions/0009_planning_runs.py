"""Additive internal planning history, no S1 changes/backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0009_planning_runs'
down_revision = '0008_forecast_execution_meta'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('planning_runs',
        sa.Column('id',sa.UUID(),nullable=False),
        sa.Column('store_id',sa.UUID(),nullable=False),
        sa.Column('actor_id',sa.UUID(),nullable=False),
        sa.Column('operation',sa.String(3),nullable=False),
        sa.Column('key_digest',sa.String(64),nullable=False),
        sa.Column('request_digest',sa.String(64),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),
        sa.Column('accepted_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('record_json',postgresql.JSONB(none_as_null=True),nullable=False),
        sa.Column('record_digest',sa.String(64),nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['store_id'],['stores.id'],ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['actor_id'],['users.id'],ondelete='RESTRICT'),
        sa.UniqueConstraint('actor_id','store_id','operation','key_digest',name='uq_planning_runs_key_scope'),
        sa.CheckConstraint("operation = 'C02'",name='ck_planning_runs_operation'),
        sa.CheckConstraint("status IN ('queued','running','completed','failed')",name='ck_planning_runs_status'),
        sa.CheckConstraint('revision >= 1',name='ck_planning_runs_revision'),
        sa.CheckConstraint("key_digest ~ '^[0-9a-f]{64}$' AND request_digest ~ '^[0-9a-f]{64}$' AND record_digest ~ '^[0-9a-f]{64}$'",name='ck_planning_runs_digests'),
        sa.CheckConstraint("jsonb_typeof(record_json) = 'object' AND record_json ? 'storage_version' AND record_json ? 'package_schema_version' AND jsonb_typeof(record_json->'package_schema_version') = 'number' AND record_json->>'storage_version' = 'planning_storage/1' AND record_json->>'package_schema_version' = '1'",name='ck_planning_runs_record_version'))


def downgrade():
    # Destructive only to this new history. Never executed against development here.
    op.drop_table('planning_runs')
