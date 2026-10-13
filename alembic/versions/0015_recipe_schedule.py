"""CAT12 retained timeline changes; dated content survives future withdrawal."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015_recipe_schedule"
down_revision = "0014_operational_import"
branch_labels = depends_on = None


def upgrade():
    op.add_column("recipes", sa.Column("assigned",sa.Boolean(),nullable=False,server_default=sa.text("true")))
    op.execute("ALTER TABLE recipes DROP CONSTRAINT ex_recipes_product_period")
    op.execute("ALTER TABLE recipes ADD CONSTRAINT ex_recipes_product_period EXCLUDE USING gist (product_id WITH =, daterange(effective_from,effective_to,'[]') WITH &&) WHERE (assigned)")
    op.create_table("recipe_schedule_changes",
        sa.Column("id",sa.UUID(),primary_key=True),
        sa.Column("store_id",sa.UUID(),sa.ForeignKey("stores.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("product_id",sa.UUID(),nullable=False),
        sa.Column("actor_id",sa.UUID(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("preview_json",postgresql.JSONB(),nullable=False),
        sa.Column("proposal_json",postgresql.JSONB(),nullable=False),
        sa.Column("receipt_json",postgresql.JSONB()),sa.Column("audit_json",postgresql.JSONB()),
        sa.ForeignKeyConstraint(["product_id","store_id"],["products.id","products.store_id"],ondelete="RESTRICT"),
        sa.CheckConstraint("(receipt_json IS NULL) = (audit_json IS NULL)",name="ck_recipe_schedule_completion"))
    op.create_index("ix_recipe_schedule_changes_store_id","recipe_schedule_changes",["store_id"])
    op.create_table("recipe_schedule_request_receipts",
        sa.Column("actor_id",sa.UUID(),sa.ForeignKey("users.id",ondelete="RESTRICT"),primary_key=True),
        sa.Column("store_id",sa.UUID(),sa.ForeignKey("stores.id",ondelete="RESTRICT"),primary_key=True),
        sa.Column("product_id",sa.UUID(),sa.ForeignKey("products.id",ondelete="RESTRICT"),primary_key=True),
        sa.Column("phase",sa.String(10),primary_key=True),sa.Column("key_digest",sa.String(64),primary_key=True),
        sa.Column("request_digest",sa.String(100),nullable=False),sa.Column("record_json",postgresql.JSONB(),nullable=False))
    op.execute("""CREATE FUNCTION recipe_schedule_evidence_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' OR OLD.receipt_json IS NOT NULL OR
         NEW.id IS DISTINCT FROM OLD.id OR NEW.store_id IS DISTINCT FROM OLD.store_id OR
         NEW.product_id IS DISTINCT FROM OLD.product_id OR NEW.actor_id IS DISTINCT FROM OLD.actor_id OR
         NEW.created_at IS DISTINCT FROM OLD.created_at OR NEW.preview_json IS DISTINCT FROM OLD.preview_json OR
         NEW.proposal_json IS DISTINCT FROM OLD.proposal_json OR NEW.receipt_json IS NULL OR NEW.audit_json IS NULL
      THEN RAISE EXCEPTION 'Recipe editor evidence is immutable' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$""")
    op.execute("CREATE TRIGGER recipe_schedule_changes_guard BEFORE UPDATE OR DELETE ON recipe_schedule_changes FOR EACH ROW EXECUTE FUNCTION recipe_schedule_evidence_guard()")
    op.execute("CREATE TRIGGER recipe_schedule_receipts_guard BEFORE UPDATE OR DELETE ON recipe_schedule_request_receipts FOR EACH ROW EXECUTE FUNCTION operational_evidence_immutable()")


def downgrade():
    # Explicitly refuse evidence loss / a state the old schema cannot represent.
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM recipes WHERE NOT assigned) OR
      EXISTS(SELECT 1 FROM recipe_schedule_changes) OR EXISTS(SELECT 1 FROM recipe_schedule_request_receipts)
      THEN RAISE EXCEPTION 'Recipe schedule evidence prevents downgrade'; END IF; END $$""")
    op.drop_table("recipe_schedule_request_receipts")
    op.drop_table("recipe_schedule_changes")
    op.execute("DROP FUNCTION recipe_schedule_evidence_guard()")
    op.execute("ALTER TABLE recipes DROP CONSTRAINT ex_recipes_product_period")
    op.drop_column("recipes","assigned")
    op.execute("ALTER TABLE recipes ADD CONSTRAINT ex_recipes_product_period EXCLUDE USING gist (product_id WITH =, daterange(effective_from,effective_to,'[]') WITH &&)")
