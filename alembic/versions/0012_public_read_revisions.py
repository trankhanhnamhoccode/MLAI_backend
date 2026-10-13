"""Transactional optimistic read versions; no business data defaults/backfill."""

from alembic import op
import sqlalchemy as sa

revision = "0012_public_read_revisions"
down_revision = "0011_staff_invitations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "public_read_revisions",
        sa.Column(
            "store_id",
            sa.UUID(),
            sa.ForeignKey("stores.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "menu_revision",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "recipe_revision",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "inventory_revision",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.execute("INSERT INTO public_read_revisions(store_id) SELECT id FROM stores")
    op.execute(
        """CREATE FUNCTION bump_public_read_revision() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE sid uuid; old_sid uuid;
    BEGIN
      IF TG_TABLE_NAME = 'stores' THEN
        IF TG_OP = 'INSERT' THEN
          INSERT INTO public_read_revisions(store_id) VALUES(NEW.id); RETURN NEW;
        ELSIF TG_OP = 'DELETE' THEN RETURN OLD;
        END IF;
        sid := NEW.id;
      ELSE
        IF TG_OP = 'DELETE' THEN sid := OLD.store_id; ELSE sid := NEW.store_id; END IF;
        IF TG_OP = 'UPDATE' AND OLD.store_id IS DISTINCT FROM NEW.store_id THEN old_sid := OLD.store_id; END IF;
      END IF;
      UPDATE public_read_revisions SET
        menu_revision = menu_revision + CASE WHEN TG_TABLE_NAME IN ('stores','products') THEN 1 ELSE 0 END,
        recipe_revision = recipe_revision + CASE WHEN TG_TABLE_NAME IN ('stores','products','ingredients','recipes','recipe_lines') THEN 1 ELSE 0 END,
        inventory_revision = inventory_revision + CASE WHEN TG_TABLE_NAME IN ('stores','inventory_lots','inventory_movements') THEN 1 ELSE 0 END
        WHERE store_id = sid OR store_id = old_sid;
      IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
    END $$"""
    )
    for table in (
        "stores",
        "products",
        "ingredients",
        "recipes",
        "recipe_lines",
        "inventory_lots",
        "inventory_movements",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_public_read_revision AFTER INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION bump_public_read_revision()"
        )


def downgrade():
    for table in (
        "stores",
        "products",
        "ingredients",
        "recipes",
        "recipe_lines",
        "inventory_lots",
        "inventory_movements",
    ):
        op.execute(f"DROP TRIGGER {table}_public_read_revision ON {table}")
    op.execute("DROP FUNCTION bump_public_read_revision()")
    op.drop_table("public_read_revisions")
