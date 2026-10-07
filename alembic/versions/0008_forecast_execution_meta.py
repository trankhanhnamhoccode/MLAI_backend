"""Purpose-specific execution metadata; no change to S1 run/result semantics."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0008_forecast_execution_meta'
down_revision = '0007_forecast_input_retention'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('forecast_execution_metadata',
        sa.Column('forecast_run_id',sa.UUID(),nullable=False),
        sa.Column('store_id',sa.UUID(),nullable=False),
        sa.Column('details_json',postgresql.JSONB(none_as_null=True),nullable=False),
        sa.PrimaryKeyConstraint('forecast_run_id'),
        sa.ForeignKeyConstraint(['forecast_run_id','store_id'],['forecast_runs.id','forecast_runs.store_id'],
            name='fk_forecast_execution_metadata_run_store',ondelete='RESTRICT'),
        sa.CheckConstraint("jsonb_typeof(details_json) = 'object'",name='ck_forecast_execution_metadata_object'),
        sa.CheckConstraint("details_json ? 'schema_version' AND jsonb_typeof(details_json->'schema_version') = 'number' AND details_json->>'schema_version' = '1'",name='ck_forecast_execution_metadata_version'))


def downgrade():
    op.drop_table('forecast_execution_metadata')
