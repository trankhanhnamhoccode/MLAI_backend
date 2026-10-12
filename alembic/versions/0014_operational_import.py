"""S4.6 source/config facts, stock receipt identity and Owner thresholds; no backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014_operational_import"
down_revision = "0013_import_staging"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_supplier_terms_id_store", "supplier_terms", ["id", "store_id"])
    op.create_unique_constraint("uq_inventory_movements_id_store", "inventory_movements", ["id", "store_id"])
    op.create_table("supplier_source_records",
        sa.Column("store_id", sa.UUID(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("source_system_key", sa.String(1000), primary_key=True),
        sa.Column("source_record_key", sa.String(1000), nullable=False),
        sa.Column("source_record_hash", sa.String(64), primary_key=True),
        sa.Column("supplier_id", sa.UUID(), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id","store_id"], ["suppliers.id","suppliers.store_id"], ondelete="RESTRICT"))
    op.create_table("term_source_records",
        sa.Column("id", sa.UUID(), sa.ForeignKey("supplier_terms.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("store_id", sa.UUID(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_system_key", sa.String(1000), nullable=False),
        sa.Column("source_record_key", sa.String(1000), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["id","store_id"],["supplier_terms.id","supplier_terms.store_id"],ondelete="RESTRICT"))
    for table, extra in (
        ("payable_fee_records", [sa.Column("resolved_references", postgresql.JSONB(), nullable=False)]),
        ("scope_declaration_records", [sa.Column("dependency_digest", sa.String(100), nullable=False)]),
    ):
        op.create_table(table,
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("store_id", sa.UUID(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("source_system_key", sa.String(1000), nullable=False),
            sa.Column("source_record_key", sa.String(1000), nullable=False),
            sa.Column("source_record_hash", sa.String(64), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("payload", postgresql.JSONB(), nullable=False),
            sa.Column("provenance", postgresql.JSONB(), nullable=False), *extra,
            sa.UniqueConstraint("store_id","source_system_key","source_record_hash","version"),
            sa.CheckConstraint("version > 0"))
    op.create_table("inventory_receipt_records",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("store_id", sa.UUID(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_system_key", sa.String(128), nullable=False),
        sa.Column("source_record_key", sa.String(128), nullable=False),
        sa.Column("ingredient_id", sa.UUID(), nullable=False), sa.Column("lot_id", sa.UUID(), nullable=False),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("payload_digest", sa.String(100), nullable=False),
        sa.Column("record_json", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("store_id","source_system_key","source_record_key"),
        sa.UniqueConstraint("lot_id"),
        sa.ForeignKeyConstraint(["lot_id","store_id","ingredient_id"], ["inventory_lots.id","inventory_lots.store_id","inventory_lots.ingredient_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("origin IN ('OPENING_STOCK','ACTUAL_RECEIPT')"))
    op.create_table("inventory_thresholds",
        sa.Column("store_id", sa.UUID(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("ingredient_id", sa.UUID(), primary_key=True),
        sa.Column("minimum_usable_quantity", sa.Numeric()), sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("version", sa.String(128), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.ForeignKeyConstraint(["ingredient_id","store_id","unit"], ["ingredients.id","ingredients.store_id","ingredients.base_unit"], ondelete="RESTRICT"),
        sa.CheckConstraint("minimum_usable_quantity IS NULL OR (minimum_usable_quantity >= 0 AND minimum_usable_quantity NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric))"))
    op.create_table("stock_request_receipts",
        sa.Column("actor_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("store_id", sa.UUID(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("operation", sa.String(200), primary_key=True), sa.Column("key_digest", sa.String(64), primary_key=True),
        sa.Column("request_digest", sa.String(100), nullable=False), sa.Column("record_json", postgresql.JSONB(), nullable=False))
    op.create_table("inventory_audit",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("store_id", sa.UUID(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("movement_id", sa.UUID(), sa.ForeignKey("inventory_movements.id", ondelete="RESTRICT")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_json", postgresql.JSONB(), nullable=False), sa.UniqueConstraint("movement_id"),
        sa.ForeignKeyConstraint(["movement_id","store_id"],["inventory_movements.id","inventory_movements.store_id"],ondelete="RESTRICT"))
    for table in ("term_source_records", "payable_fee_records", "scope_declaration_records", "inventory_receipt_records", "inventory_audit"):
        op.create_index("ix_"+table+"_store_id", table, ["store_id"])
    op.execute("""CREATE FUNCTION operational_evidence_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Operational evidence is append-only' USING ERRCODE='23514'; END $$""")
    for table in ("supplier_source_records","term_source_records","payable_fee_records","scope_declaration_records","inventory_receipt_records","stock_request_receipts","inventory_audit"):
        op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION operational_evidence_immutable()")
    op.execute("""CREATE FUNCTION bump_operational_stock_revision() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_TABLE_NAME='scope_declaration_records' THEN
        IF NEW.payload->'declaration'->>'kind' <> 'INVENTORY' THEN RETURN NEW; END IF;
      END IF;
      UPDATE public_read_revisions SET inventory_revision=inventory_revision+1 WHERE store_id=NEW.store_id;
      RETURN NEW;
    END $$""")
    for table in ("inventory_thresholds","scope_declaration_records"):
        op.execute(f"CREATE TRIGGER {table}_stock_revision AFTER INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION bump_operational_stock_revision()")


def downgrade():
    for table in ("inventory_thresholds","scope_declaration_records"):
        op.execute(f"DROP TRIGGER {table}_stock_revision ON {table}")
    op.execute("DROP FUNCTION bump_operational_stock_revision()")
    for table in ("supplier_source_records","term_source_records","payable_fee_records","scope_declaration_records","inventory_receipt_records","stock_request_receipts","inventory_audit"):
        op.execute(f"DROP TRIGGER {table}_immutable ON {table}")
    op.execute("DROP FUNCTION operational_evidence_immutable()")
    for table in ("inventory_audit","stock_request_receipts","inventory_thresholds","inventory_receipt_records","scope_declaration_records","payable_fee_records","term_source_records","supplier_source_records"):
        op.drop_table(table)
    op.drop_constraint("uq_inventory_movements_id_store", "inventory_movements", type_="unique")
    op.drop_constraint("uq_supplier_terms_id_store", "supplier_terms", type_="unique")
