"""Supplier, operational and constraint persistence only; ADR-008/009 policy."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_supplier_ops_constraints"
down_revision: str = "0003_catalog_recipe"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table('suppliers',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('store_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("name ~ '[^[:space:]]'", name='ck_suppliers_name_nonblank'),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], name='fk_suppliers_store', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id', 'store_id', name='uq_suppliers_id_store')
    )
    op.create_index('ix_suppliers_store_id', 'suppliers', ['store_id'], unique=False)
    op.create_table('supplier_terms',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('store_id', sa.UUID(), nullable=False),
        sa.Column('supplier_id', sa.UUID(), nullable=False),
        sa.Column('ingredient_id', sa.UUID(), nullable=False),
        sa.Column('unit', sa.String(length=32), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('pack_size_base_quantity', sa.Numeric(), nullable=False),
        sa.Column('minimum_order_packs', sa.Integer(), nullable=False),
        sa.Column('pack_cost', sa.Numeric(), nullable=False),
        sa.Column('lead_time_days', sa.Integer(), nullable=False),
        sa.Column('shelf_life_days', sa.Integer(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        postgresql.ExcludeConstraint((sa.column('supplier_id'), '='), (sa.column('ingredient_id'), '='), (sa.text("daterange(effective_from, effective_to, '[]')"), '&&'), where=sa.text('active'), using='gist', name='ex_supplier_terms_pair_period'),
        sa.CheckConstraint("pack_cost >= 0 AND pack_cost NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name='ck_supplier_terms_pack_cost'),
        sa.CheckConstraint("pack_size_base_quantity > 0 AND pack_size_base_quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name='ck_supplier_terms_pack_size'),
        sa.CheckConstraint('effective_to IS NULL OR effective_to >= effective_from', name='ck_supplier_terms_period'),
        sa.CheckConstraint('lead_time_days >= 0', name='ck_supplier_terms_lead_time'),
        sa.CheckConstraint('minimum_order_packs >= 1', name='ck_supplier_terms_minimum_packs'),
        sa.CheckConstraint('shelf_life_days IS NULL OR shelf_life_days >= 0', name='ck_supplier_terms_shelf_life'),
        sa.CheckConstraint('version > 0', name='ck_supplier_terms_version'),
        sa.ForeignKeyConstraint(['ingredient_id', 'store_id', 'unit'], ['ingredients.id', 'ingredients.store_id', 'ingredients.base_unit'], name='fk_supplier_terms_ingredient_store_unit', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['supplier_id', 'store_id'], ['suppliers.id', 'suppliers.store_id'], name='fk_supplier_terms_supplier_store', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('supplier_id', 'ingredient_id', 'version', name='uq_supplier_terms_pair_version')
    )
    op.create_index('ix_supplier_terms_ingredient_id', 'supplier_terms', ['ingredient_id'], unique=False)
    op.create_table('sales_daily',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('store_id', sa.UUID(), nullable=False),
        sa.Column('product_id', sa.UUID(), nullable=False),
        sa.Column('sales_date', sa.Date(), nullable=False),
        sa.Column('quantity', sa.Numeric(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("quantity >= 0 AND quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name='ck_sales_daily_quantity'),
        sa.ForeignKeyConstraint(['product_id', 'store_id'], ['products.id', 'products.store_id'], name='fk_sales_daily_product_store', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('store_id', 'product_id', 'sales_date', name='uq_sales_daily_store_product_date')
    )
    op.create_table('inventory_lots',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('store_id', sa.UUID(), nullable=False),
        sa.Column('ingredient_id', sa.UUID(), nullable=False),
        sa.Column('supplier_id', sa.UUID(), nullable=True),
        sa.Column('lot_code', sa.String(length=128), nullable=True),
        sa.Column('received_date', sa.Date(), nullable=False),
        sa.Column('expiry_date', sa.Date(), nullable=True),
        sa.Column('on_hand_quantity', sa.Numeric(), nullable=False),
        sa.Column('unit', sa.String(length=32), nullable=False),
        sa.Column('unit_cost', sa.Numeric(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("lot_code IS NULL OR lot_code ~ '[^[:space:]]'", name='ck_inventory_lots_code_nonblank'),
        sa.CheckConstraint("on_hand_quantity >= 0 AND on_hand_quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name='ck_inventory_lots_on_hand'),
        sa.CheckConstraint("unit_cost IS NULL OR (unit_cost >= 0 AND unit_cost NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))", name='ck_inventory_lots_unit_cost'),
        sa.CheckConstraint('expiry_date IS NULL OR expiry_date >= received_date', name='ck_inventory_lots_expiry'),
        sa.ForeignKeyConstraint(['ingredient_id', 'store_id', 'unit'], ['ingredients.id', 'ingredients.store_id', 'ingredients.base_unit'], name='fk_inventory_lots_ingredient_store_unit', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['supplier_id', 'store_id'], ['suppliers.id', 'suppliers.store_id'], name='fk_inventory_lots_supplier_store', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id', 'store_id', 'ingredient_id', name='uq_inventory_lots_id_store_ingredient')
    )
    op.create_index('ix_inventory_lots_store_ingredient_expiry', 'inventory_lots', ['store_id', 'ingredient_id', 'expiry_date'], unique=False)
    op.create_table('inventory_movements',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('store_id', sa.UUID(), nullable=False),
        sa.Column('lot_id', sa.UUID(), nullable=False),
        sa.Column('ingredient_id', sa.UUID(), nullable=False),
        sa.Column('movement_type', sa.String(length=24), nullable=False),
        sa.Column('quantity_delta', sa.Numeric(), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reference_type', sa.String(length=64), nullable=True),
        sa.Column('reference_id', sa.Text(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("(movement_type = 'RECEIPT' AND quantity_delta > 0) OR (movement_type IN ('USAGE', 'WASTE', 'EXPIRED') AND quantity_delta < 0) OR movement_type IN ('COUNT_CORRECTION', 'MANUAL_ADJUSTMENT')", name='ck_inventory_movements_sign'),
        sa.CheckConstraint("(reference_type IS NULL AND reference_id IS NULL) OR (reference_type IS NOT NULL AND reference_id IS NOT NULL AND reference_type ~ '[^[:space:]]' AND reference_id ~ '[^[:space:]]')", name='ck_inventory_movements_reference_pair'),
        sa.CheckConstraint("movement_type IN ('RECEIPT', 'USAGE', 'WASTE', 'EXPIRED', 'COUNT_CORRECTION', 'MANUAL_ADJUSTMENT')", name='ck_inventory_movements_type'),
        sa.CheckConstraint("quantity_delta <> 0 AND quantity_delta NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name='ck_inventory_movements_delta'),
        sa.ForeignKeyConstraint(['lot_id', 'store_id', 'ingredient_id'], ['inventory_lots.id', 'inventory_lots.store_id', 'inventory_lots.ingredient_id'], name='fk_inventory_movements_lot_store_ingredient', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_inventory_movements_lot_occurred', 'inventory_movements', ['lot_id', 'occurred_at'], unique=False)
    op.create_table('business_constraints',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('store_id', sa.UUID(), nullable=False),
        sa.Column('scope_type', sa.String(length=10), nullable=False),
        sa.Column('scope_id', sa.UUID(), nullable=True),
        sa.Column('constraint_type', sa.String(length=24), nullable=False),
        sa.Column('numeric_value', sa.Numeric(), nullable=False),
        sa.Column('unit', sa.String(length=32), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        postgresql.ExcludeConstraint((sa.column('store_id'), '='), (sa.column('scope_type'), '='), (sa.text('coalesce(scope_id, store_id)'), '='), (sa.column('constraint_type'), '='), (sa.text("daterange(effective_from, effective_to, '[]')"), '&&'), where=sa.text('active'), using='gist', name='ex_business_constraints_scope_period'),
        sa.CheckConstraint("(scope_type = 'STORE' AND scope_id IS NULL AND constraint_type = 'BUDGET_LIMIT' AND unit ~ '^[A-Z]{3}$') OR (scope_type = 'INGREDIENT' AND scope_id IS NOT NULL AND constraint_type = 'MIN_SAFETY_STOCK')", name='ck_business_constraints_registry_scope'),
        sa.CheckConstraint("numeric_value >= 0 AND numeric_value NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name='ck_business_constraints_numeric_value'),
        sa.CheckConstraint('effective_to IS NULL OR effective_to >= effective_from', name='ck_business_constraints_period'),
        sa.CheckConstraint('version > 0', name='ck_business_constraints_version'),
        sa.ForeignKeyConstraint(['scope_id', 'store_id', 'unit'], ['ingredients.id', 'ingredients.store_id', 'ingredients.base_unit'], name='fk_business_constraints_ingredient_scope_unit', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], name='fk_business_constraints_store', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('store_id', 'scope_type', 'scope_id', 'constraint_type', 'version', name='uq_business_constraints_scope_version', postgresql_nulls_not_distinct=True)
    )


def downgrade() -> None:
    op.drop_table("business_constraints")
    op.drop_table("inventory_movements")
    op.drop_table("inventory_lots")
    op.drop_table("sales_daily")
    op.drop_table("supplier_terms")
    op.drop_table("suppliers")
    # btree_gist belongs to the parent migration and remains installed.
