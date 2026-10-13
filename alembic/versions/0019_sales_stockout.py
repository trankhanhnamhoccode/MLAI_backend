"""A1 observed stockout; independent of Auth migration 0018."""
from alembic import op
import sqlalchemy as sa

revision = '0019_sales_stockout'
down_revision = '0017_planning_exports'
branch_labels = depends_on = None


def upgrade():
    op.add_column('sales_daily', sa.Column('is_stockout', sa.Boolean(), nullable=True))


def downgrade():
    if op.get_bind().scalar(sa.text(
        'SELECT EXISTS(SELECT 1 FROM sales_daily WHERE is_stockout IS NOT NULL)'
    )):
        raise RuntimeError('Refusing downgrade of retained stockout observations')
    op.drop_column('sales_daily', 'is_stockout')
