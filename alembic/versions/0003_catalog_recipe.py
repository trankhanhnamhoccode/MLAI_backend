"""Catalog + Recipe persistence only, including database graph integrity."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_catalog_recipe"
down_revision: str = "0002_identity_store"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # PostgreSQL UUID equality + date ranges in one exclusion index.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(64), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("selling_unit", sa.String(32), nullable=False),
        sa.Column("price", sa.Numeric(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_products_store", ondelete="RESTRICT"),
        sa.UniqueConstraint("store_id", "sku", name="uq_products_store_sku"),
        sa.UniqueConstraint("id", "store_id", name="uq_products_id_store"),
        sa.CheckConstraint("name ~ '[^[:space:]]'", name="ck_products_name_nonblank"),
        sa.CheckConstraint("sku IS NULL OR sku ~ '[^[:space:]]'", name="ck_products_sku_nonblank"),
        sa.CheckConstraint("selling_unit ~ '[^[:space:]]'", name="ck_products_selling_unit_nonblank"),
        sa.CheckConstraint("price IS NULL OR (price >= 0 AND price NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))", name="ck_products_price"),
    )
    op.create_table(
        "ingredients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(64), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("base_unit", sa.String(32), nullable=False),
        sa.Column("expiry_tracking", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_ingredients_store", ondelete="RESTRICT"),
        sa.UniqueConstraint("store_id", "sku", name="uq_ingredients_store_sku"),
        sa.UniqueConstraint("id", "store_id", "base_unit", name="uq_ingredients_id_store_unit"),
        sa.CheckConstraint("name ~ '[^[:space:]]'", name="ck_ingredients_name_nonblank"),
        sa.CheckConstraint("sku IS NULL OR sku ~ '[^[:space:]]'", name="ck_ingredients_sku_nonblank"),
        sa.CheckConstraint("base_unit ~ '[^[:space:]]'", name="ck_ingredients_base_unit_nonblank"),
    )
    op.create_table(
        "recipes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("yield_quantity", sa.Numeric(), nullable=False),
        sa.Column("process_loss_rate", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_recipes_store", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id", "store_id"], ["products.id", "products.store_id"], name="fk_recipes_product_store", ondelete="RESTRICT"),
        sa.UniqueConstraint("product_id", "version", name="uq_recipes_product_version"),
        sa.UniqueConstraint("id", "store_id", name="uq_recipes_id_store"),
        sa.CheckConstraint("version > 0", name="ck_recipes_version"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_recipes_period"),
        sa.CheckConstraint("yield_quantity > 0 AND yield_quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name="ck_recipes_yield"),
        sa.CheckConstraint("process_loss_rate >= 0 AND process_loss_rate < 1", name="ck_recipes_loss"),
        postgresql.ExcludeConstraint(("product_id", "="), (sa.text("daterange(effective_from, effective_to, '[]')"), "&&"), name="ex_recipes_product_period", using="gist"),
    )
    op.create_table(
        "recipe_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingredient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["recipe_id", "store_id"], ["recipes.id", "recipes.store_id"], name="fk_recipe_lines_recipe_store", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ingredient_id", "store_id", "unit"], ["ingredients.id", "ingredients.store_id", "ingredients.base_unit"], name="fk_recipe_lines_ingredient_store_unit", ondelete="RESTRICT"),
        sa.UniqueConstraint("recipe_id", "ingredient_id", name="uq_recipe_lines_recipe_ingredient"),
        sa.CheckConstraint("quantity > 0 AND quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name="ck_recipe_lines_quantity"),
    )
    op.create_index("ix_recipe_lines_ingredient_id", "recipe_lines", ["ingredient_id"])


def downgrade() -> None:
    op.drop_index("ix_recipe_lines_ingredient_id", table_name="recipe_lines")
    op.drop_table("recipe_lines")
    op.drop_table("recipes")
    op.drop_table("ingredients")
    op.drop_table("products")
    # Keep btree_gist: it may have existed before this migration or be shared.
