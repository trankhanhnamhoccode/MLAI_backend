"""A2 recorded history and permission catalogue; independent of Auth head."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0021_import_support_history'
down_revision = '0019_sales_stockout'
branch_labels = depends_on = None

OLD_CATALOGUE = "permission IN ('budget.read','budget.update','import.analyze','import.commit','import.create','import.preview','import.read','import.upload','ingredient.create','ingredient.read','inventory.count.correct','inventory.read','inventory.receive','mapping.propose','mapping.read','menu.read','planning.context.read','planning.export','planning.requirements.create','planning.requirements.manage','planning.requirements.read','planning.result.read','planning.run','procurement.cost.read','product.create','recipe.create_version','recipe.manage_effectivity','recipe.read','sales.correct','sales.merge','sales.read','sales.record','supplier.create','supplier.fees.manage','supplier.read','supplier.terms.correct','supplier.terms.create')"
NEW_CATALOGUE = "permission IN ('budget.read','budget.update','calendar.read','calendar.write','import.analyze','import.commit','import.create','import.preview','import.read','import.upload','ingredient.create','ingredient.read','inventory.count.correct','inventory.read','inventory.receive','mapping.propose','mapping.read','menu.read','planning.context.read','planning.export','planning.requirements.create','planning.requirements.manage','planning.requirements.read','planning.result.read','planning.run','procurement.cost.read','product.create','purchase.history.read','purchase.history.write','recipe.create_version','recipe.manage_effectivity','recipe.read','sales.correct','sales.merge','sales.read','sales.record','supplier.create','supplier.fees.manage','supplier.read','supplier.terms.correct','supplier.terms.create','usage.history.read','usage.history.write')"
NEW_PERMISSIONS = ('calendar.read', 'calendar.write', 'purchase.history.read', 'purchase.history.write', 'usage.history.read', 'usage.history.write')


def upgrade():
    op.drop_constraint('ck_membership_grants_catalogue', 'membership_grants', type_='check')
    op.create_check_constraint('ck_membership_grants_catalogue', 'membership_grants', NEW_CATALOGUE)
    op.create_table('import_history_records',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('store_id', sa.UUID(), sa.ForeignKey('stores.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('domain', sa.String(32), nullable=False),
        sa.Column('source_system_key', sa.String(128), nullable=False),
        sa.Column('report_type', sa.String(128), nullable=False),
        sa.Column('source_record_key', sa.String(1000), nullable=False),
        sa.Column('source_record_hash', sa.String(64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('provenance', postgresql.JSONB(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('store_id','domain','source_system_key','report_type','source_record_hash','version'),
        sa.CheckConstraint('version > 0'),
        sa.CheckConstraint("domain IN ('calendar_events','promotion_observations','usage_history','purchase_history')"),
        sa.CheckConstraint("jsonb_typeof(payload) = 'object' AND jsonb_typeof(provenance) = 'object'"))
    op.create_index('ix_import_history_records_store_id', 'import_history_records', ['store_id'])
    op.execute('CREATE TRIGGER import_history_immutable BEFORE UPDATE OR DELETE ON import_history_records FOR EACH ROW EXECUTE FUNCTION operational_evidence_immutable()')


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM import_history_records)')):
        raise RuntimeError('Retained A2 history prevents downgrade')
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM membership_grants WHERE permission = ANY(:permissions))'), {'permissions': list(NEW_PERMISSIONS)}):
        raise RuntimeError('A2 granted permissions prevent downgrade')
    op.drop_table('import_history_records')
    op.drop_constraint('ck_membership_grants_catalogue', 'membership_grants', type_='check')
    op.create_check_constraint('ck_membership_grants_catalogue', 'membership_grants', OLD_CATALOGUE)
