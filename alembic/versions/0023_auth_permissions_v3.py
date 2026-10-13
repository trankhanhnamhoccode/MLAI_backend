"""Auth catalogue v3 CHECK only; no grants backfill or Import domain tables."""
from alembic import op
import sqlalchemy as sa

revision = '0023_auth_permissions_v3'
down_revision = '0022_invitation_decline'
branch_labels = depends_on = None

OLD_CATALOGUE = "permission IN ('budget.read','budget.update','import.analyze','import.commit','import.create','import.preview','import.read','import.upload','ingredient.create','ingredient.read','inventory.count.correct','inventory.read','inventory.receive','mapping.propose','mapping.read','menu.read','planning.context.read','planning.export','planning.requirements.create','planning.requirements.manage','planning.requirements.read','planning.result.read','planning.run','procurement.cost.read','product.create','recipe.create_version','recipe.manage_effectivity','recipe.read','sales.correct','sales.merge','sales.read','sales.record','supplier.create','supplier.fees.manage','supplier.read','supplier.terms.correct','supplier.terms.create')"
NEW_CATALOGUE = "permission IN ('budget.read','budget.update','calendar.read','calendar.write','import.analyze','import.commit','import.create','import.preview','import.read','import.upload','ingredient.create','ingredient.read','inventory.count.correct','inventory.read','inventory.receive','mapping.propose','mapping.read','menu.read','planning.context.read','planning.export','planning.requirements.create','planning.requirements.manage','planning.requirements.read','planning.result.read','planning.run','procurement.cost.read','product.create','purchase.history.read','purchase.history.write','recipe.create_version','recipe.manage_effectivity','recipe.read','sales.correct','sales.merge','sales.read','sales.record','supplier.create','supplier.fees.manage','supplier.read','supplier.terms.correct','supplier.terms.create','usage.history.read','usage.history.write')"
NEW_PERMISSIONS = ('calendar.read', 'calendar.write', 'purchase.history.read', 'purchase.history.write', 'usage.history.read', 'usage.history.write')


def upgrade():
    op.drop_constraint('ck_membership_grants_catalogue', 'membership_grants', type_='check')
    op.create_check_constraint('ck_membership_grants_catalogue', 'membership_grants', NEW_CATALOGUE)


def downgrade():
    # Integration-only repair: Import may still require v3 after this downgrade.
    from alembic.script import ScriptDirectory
    script = ScriptDirectory.from_config(op.get_context().config)
    import_requires_v3 = any(
        revision.revision == '0021_import_support_history'
        for head in op.get_context().get_current_heads()
        for revision in script.walk_revisions(base='base', head=head)
    )
    if import_requires_v3:
        return
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM membership_grants WHERE permission = ANY(:permissions))'), {'permissions': list(NEW_PERMISSIONS)}):
        raise RuntimeError('Retained v3 grants prevent downgrade')
    op.drop_constraint('ck_membership_grants_catalogue', 'membership_grants', type_='check')
    op.create_check_constraint('ck_membership_grants_catalogue', 'membership_grants', OLD_CATALOGUE)
