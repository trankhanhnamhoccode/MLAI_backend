"""S4.8 Store configuration and retained evidence, without business backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0016_planning_configuration'
down_revision = '0015_recipe_schedule'
branch_labels = depends_on = None


def store_column(primary=False):
    return sa.Column('store_id', sa.UUID(), sa.ForeignKey('stores.id', ondelete='RESTRICT'), primary_key=primary, nullable=False)


def upgrade():
    op.create_table('planning_defaults', store_column(True),
        sa.Column('version',sa.String(128),nullable=False),sa.Column('requirements_json',JSONB(),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True)))
    op.create_table('planning_budgets', store_column(True),sa.Column('version',sa.String(128),nullable=False),
        sa.Column('amount',sa.String(37),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_by',sa.UUID(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False))
    op.create_table('saved_requirements',sa.Column('id',sa.UUID(),primary_key=True),store_column(),
        sa.Column('name',sa.String(200),nullable=False),sa.Column('state',sa.String(10),nullable=False),
        sa.Column('version',sa.String(128),nullable=False),sa.Column('requirements_json',JSONB(),nullable=False),
        sa.Column('default_reference_json',JSONB()),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('created_by',sa.UUID(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('updated_by',sa.UUID(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.UniqueConstraint('id','store_id'))
    op.create_index('ix_saved_requirements_store_id','saved_requirements',['store_id'])
    op.create_table('planning_configuration_events',sa.Column('id',sa.UUID(),primary_key=True),store_column(),
        sa.Column('actor_id',sa.UUID(),sa.ForeignKey('users.id',ondelete='RESTRICT')),
        sa.Column('occurred_at',sa.DateTime(timezone=True),nullable=False),sa.Column('record_json',JSONB(),nullable=False))
    op.create_index('ix_planning_configuration_events_store_id','planning_configuration_events',['store_id'])
    op.create_table('planning_configuration_revisions',store_column(True),
        sa.Column('resource',sa.String(100),primary_key=True),sa.Column('version',sa.String(128),primary_key=True),
        sa.Column('record_json',JSONB(),nullable=False))
    op.create_table('planning_configuration_receipts',
        sa.Column('actor_id',sa.UUID(),sa.ForeignKey('users.id',ondelete='RESTRICT'),primary_key=True),store_column(True),
        sa.Column('operation',sa.String(100),primary_key=True),sa.Column('key_digest',sa.String(64),primary_key=True),
        sa.Column('request_digest',sa.String(100),nullable=False),sa.Column('status_code',sa.Integer(),nullable=False),
        sa.Column('record_json',JSONB(),nullable=False))
    for table in ('planning_configuration_events','planning_configuration_revisions','planning_configuration_receipts'):
        op.execute(f'CREATE TRIGGER {table}_guard BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION operational_evidence_immutable()')
    op.execute("""CREATE FUNCTION saved_requirement_owner_guard() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN IF TG_OP='DELETE' OR NEW.id IS DISTINCT FROM OLD.id OR
      NEW.store_id IS DISTINCT FROM OLD.store_id OR NEW.created_by IS DISTINCT FROM OLD.created_by OR
      NEW.created_at IS DISTINCT FROM OLD.created_at THEN RAISE EXCEPTION 'Saved creator/history immutable' USING ERRCODE='23514'; END IF;
      RETURN NEW; END $$""")
    op.execute('CREATE TRIGGER saved_requirement_guard BEFORE UPDATE OR DELETE ON saved_requirements FOR EACH ROW EXECUTE FUNCTION saved_requirement_owner_guard()')
    op.create_table('model_serving_configurations',store_column(True),sa.Column('version',sa.String(128),nullable=False),
        sa.Column('configuration_json',JSONB(),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('operator_reference',sa.String(200),nullable=False),sa.Column('evidence_reference',sa.String(1000),nullable=False))
    op.create_table('forecast_serving_identities',sa.Column('forecast_run_id',sa.UUID(),primary_key=True),store_column(),
        sa.Column('identity_digest',sa.String(100),nullable=False),sa.Column('identity_json',JSONB(),nullable=False),
        sa.ForeignKeyConstraint(['forecast_run_id','store_id'],['forecast_runs.id','forecast_runs.store_id'],ondelete='RESTRICT'))
    op.create_index('ix_forecast_serving_identities_store_id','forecast_serving_identities',['store_id'])
    op.create_index('ix_forecast_serving_identities_identity_digest','forecast_serving_identities',['identity_digest'])
    op.execute('CREATE TRIGGER forecast_serving_identities_guard BEFORE UPDATE OR DELETE ON forecast_serving_identities FOR EACH ROW EXECUTE FUNCTION operational_evidence_immutable()')


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM planning_configuration_revisions) OR
      EXISTS(SELECT 1 FROM planning_configuration_events) OR EXISTS(SELECT 1 FROM planning_configuration_receipts) OR
      EXISTS(SELECT 1 FROM saved_requirements) OR EXISTS(SELECT 1 FROM planning_budgets) OR
      EXISTS(SELECT 1 FROM planning_defaults) OR EXISTS(SELECT 1 FROM model_serving_configurations) OR
      EXISTS(SELECT 1 FROM forecast_serving_identities) THEN RAISE EXCEPTION 'Planning configuration evidence prevents downgrade'; END IF; END $$""")
    for table in ('forecast_serving_identities','model_serving_configurations','planning_configuration_receipts','planning_configuration_revisions','planning_configuration_events',
                  'saved_requirements','planning_budgets','planning_defaults'):
        op.drop_table(table)
    op.execute('DROP FUNCTION saved_requirement_owner_guard()')
