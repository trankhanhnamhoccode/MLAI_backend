"""Identity + Store schema cluster only; no public API or auth behavior."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_identity_store"
down_revision: str = "0001_scaffold"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("email <> '' AND email = lower(email) AND email !~ '[[:space:]]'", name="ck_users_email_canonical"),
        sa.CheckConstraint("password_hash ~ '[^[:space:]]'", name="ck_users_password_hash_nonblank"),
        sa.CheckConstraint("display_name ~ '[^[:space:]]'", name="ck_users_display_name_nonblank"),
    )
    op.create_table(
        "stores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default=sa.text("'Asia/Ho_Chi_Minh'")),
        sa.Column("currency", sa.String(3), nullable=False, server_default=sa.text("'VND'")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("name ~ '[^[:space:]]'", name="ck_stores_name_nonblank"),
        sa.CheckConstraint("timezone ~ '[^[:space:]]'", name="ck_stores_timezone_nonblank"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_stores_currency_shape"),
    )
    op.create_table(
        "store_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(5), nullable=False),
        sa.Column("delegated_permissions", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_store_memberships_store", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_store_memberships_user", ondelete="RESTRICT"),
        sa.UniqueConstraint("store_id", "user_id", name="uq_store_memberships_store_user"),
        sa.CheckConstraint("role IN ('OWNER', 'STAFF')", name="ck_store_memberships_role"),
        sa.CheckConstraint("delegated_permissions = '[]'::jsonb", name="ck_store_memberships_permissions_reserved"),
    )
    op.create_index("ix_store_memberships_user_id", "store_memberships", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_store_memberships_user_id", table_name="store_memberships")
    op.drop_table("store_memberships")
    op.drop_table("stores")
    op.drop_table("users")
