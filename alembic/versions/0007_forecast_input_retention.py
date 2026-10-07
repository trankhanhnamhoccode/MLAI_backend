"""Retained prepared input; downgrade loses inputs, leaves runs/predictions intact."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0007_forecast_input_retention'
down_revision = '0006_forecast_decision_persist'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('forecast_run_inputs',
        sa.Column('forecast_run_id', sa.UUID(), nullable=False),
        sa.Column('store_id', sa.UUID(), nullable=False),
        sa.Column('prepared_json', postgresql.JSONB(none_as_null=True), nullable=False),
        sa.Column('serialization_version', sa.Integer(), nullable=False),
        sa.Column('digest', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('forecast_run_id'),
        sa.ForeignKeyConstraint(['forecast_run_id', 'store_id'], ['forecast_runs.id', 'forecast_runs.store_id'],
                                name='fk_forecast_run_inputs_run_store', ondelete='RESTRICT'),
        sa.CheckConstraint("jsonb_typeof(prepared_json) = 'object'", name='ck_forecast_run_inputs_object'),
        sa.CheckConstraint('serialization_version > 0', name='ck_forecast_run_inputs_version'),
        sa.CheckConstraint("digest ~ '^[0-9a-f]{64}$'", name='ck_forecast_run_inputs_digest'))


def downgrade() -> None:
    op.drop_table('forecast_run_inputs')
