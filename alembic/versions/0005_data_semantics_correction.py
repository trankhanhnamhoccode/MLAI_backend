"""Preserve unknown receipt dates without manufacturing business facts."""
from alembic import op
import sqlalchemy as sa

revision = "0005_data_semantics_correction"
down_revision = "0004_supplier_ops_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("inventory_lots", "received_date", existing_type=sa.Date(), nullable=True)
    op.drop_constraint("ck_inventory_lots_expiry", "inventory_lots", type_="check")
    op.create_check_constraint("ck_inventory_lots_expiry", "inventory_lots",
                               "received_date IS NULL OR expiry_date IS NULL OR expiry_date >= received_date")


def downgrade() -> None:
    # Refuse NULL rows. Never substitute snapshot/upload/current dates.
    # PostgreSQL transactional DDL keeps revision/schema intact on failure.
    op.alter_column("inventory_lots", "received_date", existing_type=sa.Date(), nullable=False)
    op.drop_constraint("ck_inventory_lots_expiry", "inventory_lots", type_="check")
    op.create_check_constraint("ck_inventory_lots_expiry", "inventory_lots",
                               "expiry_date IS NULL OR expiry_date >= received_date")
