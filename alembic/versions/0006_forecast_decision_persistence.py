"""forecast_decision_persistence

Revision ID: 0006_forecast_decision_persist
Revises: 0005_data_semantics_correction
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0006_forecast_decision_persist'
down_revision: Union[str, Sequence[str], None] = '0005_data_semantics_correction'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('forecast_runs',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('store_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('training_start_date', sa.Date(), nullable=False),
    sa.Column('training_end_date', sa.Date(), nullable=False),
    sa.Column('forecast_start_date', sa.Date(), nullable=False),
    sa.Column('forecast_end_date', sa.Date(), nullable=False),
    sa.Column('model_type', sa.String(length=128), nullable=False),
    sa.Column('model_version', sa.String(length=128), nullable=False),
    sa.Column('artifact_key', sa.Text(), nullable=True),
    sa.Column('metrics_json', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True),
    sa.Column('input_fingerprint', sa.String(length=128), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error_code', sa.String(length=64), nullable=True),
    sa.Column('error_summary', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(error_code IS NULL OR error_code ~ '[^[:space:]]') AND (error_summary IS NULL OR error_summary ~ '[^[:space:]]')", name='ck_forecast_runs_error_nonblank'),
    sa.CheckConstraint("(status = 'RUNNING' AND completed_at IS NULL AND error_code IS NULL AND error_summary IS NULL) OR (status = 'COMPLETED' AND completed_at IS NOT NULL AND input_fingerprint IS NOT NULL AND error_code IS NULL AND error_summary IS NULL) OR (status = 'FAILED' AND completed_at IS NOT NULL AND error_code IS NOT NULL AND error_summary IS NOT NULL)", name='ck_forecast_runs_state'),
    sa.CheckConstraint("artifact_key IS NULL OR artifact_key ~ '[^[:space:]]'", name='ck_forecast_runs_artifact_key'),
    sa.CheckConstraint("input_fingerprint IS NULL OR input_fingerprint ~ '[^[:space:]]'", name='ck_forecast_runs_fingerprint'),
    sa.CheckConstraint("metrics_json IS NULL OR jsonb_typeof(metrics_json) = 'object'", name='ck_forecast_runs_metrics_object'),
    sa.CheckConstraint("model_type ~ '[^[:space:]]' AND model_version ~ '[^[:space:]]'", name='ck_forecast_runs_model_metadata'),
    sa.CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED')", name='ck_forecast_runs_status'),
    sa.CheckConstraint('completed_at IS NULL OR completed_at >= started_at', name='ck_forecast_runs_timestamps'),
    sa.CheckConstraint('forecast_start_date <= forecast_end_date', name='ck_forecast_runs_horizon'),
    sa.CheckConstraint('training_start_date <= training_end_date', name='ck_forecast_runs_training_window'),
    sa.ForeignKeyConstraint(['store_id'], ['stores.id'], name='fk_forecast_runs_store', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'store_id', name='uq_forecast_runs_id_store')
    )
    op.create_index('ix_forecast_runs_store_created', 'forecast_runs', ['store_id', 'created_at'], unique=False)
    op.create_table('decision_runs',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('store_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('forecast_run_id', sa.UUID(), nullable=False),
    sa.Column('planning_start_date', sa.Date(), nullable=False),
    sa.Column('planning_end_date', sa.Date(), nullable=False),
    sa.Column('package_schema_version', sa.Integer(), nullable=True),
    sa.Column('input_fingerprint', sa.String(length=128), nullable=True),
    sa.Column('input_snapshot_json', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True),
    sa.Column('decision_package_json', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True),
    sa.Column('recommended_strategy', sa.String(length=16), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error_code', sa.String(length=64), nullable=True),
    sa.Column('error_summary', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(error_code IS NULL OR error_code ~ '[^[:space:]]') AND (error_summary IS NULL OR error_summary ~ '[^[:space:]]')", name='ck_decision_runs_error_nonblank'),
    sa.CheckConstraint("(status = 'RUNNING' AND completed_at IS NULL AND decision_package_json IS NULL AND recommended_strategy IS NULL AND error_code IS NULL AND error_summary IS NULL) OR (status = 'COMPLETED' AND package_schema_version IS NOT NULL AND input_fingerprint IS NOT NULL AND input_snapshot_json IS NOT NULL AND decision_package_json IS NOT NULL AND recommended_strategy IS NOT NULL AND completed_at IS NOT NULL AND error_code IS NULL AND error_summary IS NULL) OR (status = 'FAILED' AND completed_at IS NOT NULL AND decision_package_json IS NULL AND recommended_strategy IS NULL AND error_code IS NOT NULL AND error_summary IS NOT NULL)", name='ck_decision_runs_state'),
    sa.CheckConstraint("decision_package_json IS NULL OR jsonb_typeof(decision_package_json) = 'object'", name='ck_decision_runs_package_object'),
    sa.CheckConstraint("input_fingerprint IS NULL OR input_fingerprint ~ '[^[:space:]]'", name='ck_decision_runs_fingerprint'),
    sa.CheckConstraint("input_snapshot_json IS NULL OR jsonb_typeof(input_snapshot_json) = 'object'", name='ck_decision_runs_snapshot_object'),
    sa.CheckConstraint("recommended_strategy IS NULL OR recommended_strategy IN ('LEAN', 'BALANCED', 'PROTECTED')", name='ck_decision_runs_strategy'),
    sa.CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED')", name='ck_decision_runs_status'),
    sa.CheckConstraint('completed_at IS NULL OR completed_at >= started_at', name='ck_decision_runs_timestamps'),
    sa.CheckConstraint('decision_package_json IS NULL OR package_schema_version IS NOT NULL', name='ck_decision_runs_package_version_required'),
    sa.CheckConstraint('package_schema_version IS NULL OR package_schema_version > 0', name='ck_decision_runs_package_version'),
    sa.CheckConstraint('planning_start_date <= planning_end_date', name='ck_decision_runs_planning_window'),
    sa.ForeignKeyConstraint(['forecast_run_id', 'store_id'], ['forecast_runs.id', 'forecast_runs.store_id'], name='fk_decision_runs_forecast_store', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_decision_runs_forecast', 'decision_runs', ['forecast_run_id'], unique=False)
    op.create_index('ix_decision_runs_store_created', 'decision_runs', ['store_id', 'created_at'], unique=False)
    op.create_table('forecast_predictions',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('forecast_run_id', sa.UUID(), nullable=False),
    sa.Column('store_id', sa.UUID(), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('forecast_date', sa.Date(), nullable=False),
    sa.Column('p25', sa.Numeric(), nullable=False),
    sa.Column('p50', sa.Numeric(), nullable=False),
    sa.Column('p75', sa.Numeric(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("0 <= p25 AND p25 <= p50 AND p50 <= p75 AND p25 NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) AND p50 NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) AND p75 NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name='ck_forecast_predictions_quantiles'),
    sa.ForeignKeyConstraint(['forecast_run_id', 'store_id'], ['forecast_runs.id', 'forecast_runs.store_id'], name='fk_forecast_predictions_run_store', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['product_id', 'store_id'], ['products.id', 'products.store_id'], name='fk_forecast_predictions_product_store', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('forecast_run_id', 'product_id', 'forecast_date', name='uq_forecast_predictions_run_product_date')
    )
    op.create_index('ix_forecast_predictions_product', 'forecast_predictions', ['product_id'], unique=False)
    op.create_index('ix_forecast_predictions_run_date', 'forecast_predictions', ['forecast_run_id', 'forecast_date'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_forecast_predictions_run_date', table_name='forecast_predictions')
    op.drop_index('ix_forecast_predictions_product', table_name='forecast_predictions')
    op.drop_table('forecast_predictions')
    op.drop_index('ix_decision_runs_store_created', table_name='decision_runs')
    op.drop_index('ix_decision_runs_forecast', table_name='decision_runs')
    op.drop_table('decision_runs')
    op.drop_index('ix_forecast_runs_store_created', table_name='forecast_runs')
    op.drop_table('forecast_runs')
