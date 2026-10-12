"""S4.1 additive auth storage. No ownership/grants/credentials backfill."""
from alembic import op
import sqlalchemy as sa

revision = "0010_auth_sessions"
down_revision = "0009_planning_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("store_memberships", sa.Column("authorization_revision", sa.Integer(), nullable=False, server_default=sa.text("1")))
    op.create_check_constraint("ck_store_memberships_authorization_revision", "store_memberships", "authorization_revision >= 1")
    op.create_table("auth_accounts",
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("credential_revision", sa.Integer(), nullable=False),
        sa.Column("credential_ready", sa.Boolean(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_email", sa.String(320), nullable=False),
        sa.Column("verification_reference", sa.String(1000), nullable=False),
        sa.CheckConstraint("credential_revision >= 1", name="ck_auth_accounts_revision"))
    op.create_table("auth_sessions",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("credential_revision", sa.Integer(), nullable=False),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("remember_me", sa.Boolean(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("absolute_expires_at > issued_at AND idle_expires_at > issued_at", name="ck_auth_sessions_expiry"))
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_table("credential_tokens",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(5), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("purpose IN ('SETUP','RESET') AND revision >= 1", name="ck_credential_tokens_purpose_revision"))
    op.create_index("ix_credential_tokens_user_id", "credential_tokens", ["user_id"])
    op.create_table("membership_grants",
        sa.Column("membership_id", sa.UUID(), sa.ForeignKey("store_memberships.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("permission", sa.String(64), primary_key=True),
        sa.CheckConstraint("permission IN ('budget.read','budget.update','import.analyze','import.commit','import.create','import.preview','import.read','import.upload','ingredient.create','ingredient.read','inventory.count.correct','inventory.read','inventory.receive','mapping.propose','mapping.read','menu.read','planning.context.read','planning.export','planning.requirements.create','planning.requirements.manage','planning.requirements.read','planning.result.read','planning.run','procurement.cost.read','product.create','recipe.create_version','recipe.manage_effectivity','recipe.read','sales.correct','sales.merge','sales.read','sales.record','supplier.create','supplier.fees.manage','supplier.read','supplier.terms.correct','supplier.terms.create')", name="ck_membership_grants_catalogue"))
    op.create_table("auth_audit",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("store_id", sa.UUID(), sa.ForeignKey("stores.id", ondelete="RESTRICT")),
        sa.Column("operator_reference", sa.String(200)),
        sa.Column("evidence_reference", sa.String(1000)),
        sa.Column("request_reference", sa.String(200), nullable=False, unique=True),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("auth_rate_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    # Direct S1 User deactivation also revokes the new sessions atomically.
    op.execute("""CREATE FUNCTION revoke_auth_sessions_on_deactivation() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
      IF OLD.active AND NOT NEW.active THEN
        UPDATE auth_sessions SET revoked_at = CURRENT_TIMESTAMP
        WHERE user_id = NEW.id AND revoked_at IS NULL;
      END IF; RETURN NEW; END $$""")
    op.execute("CREATE TRIGGER users_auth_deactivation AFTER UPDATE OF active ON users FOR EACH ROW EXECUTE FUNCTION revoke_auth_sessions_on_deactivation()")
    op.execute("""CREATE FUNCTION bump_membership_authorization_revision() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
      IF OLD.active IS DISTINCT FROM NEW.active OR OLD.role IS DISTINCT FROM NEW.role THEN
        NEW.authorization_revision := OLD.authorization_revision + 1;
      END IF; RETURN NEW; END $$""")
    op.execute("CREATE TRIGGER memberships_auth_revision BEFORE UPDATE OF active, role ON store_memberships FOR EACH ROW EXECUTE FUNCTION bump_membership_authorization_revision()")
    op.execute("""CREATE FUNCTION bump_grant_authorization_revision() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP = 'UPDATE' THEN
        IF OLD.membership_id = NEW.membership_id AND OLD.permission = NEW.permission THEN RETURN NEW; END IF;
        UPDATE store_memberships SET authorization_revision = authorization_revision + 1 WHERE id = OLD.membership_id;
      ELSIF TG_OP = 'DELETE' THEN
        UPDATE store_memberships SET authorization_revision = authorization_revision + 1 WHERE id = OLD.membership_id;
        RETURN OLD;
      END IF;
      UPDATE store_memberships SET authorization_revision = authorization_revision + 1 WHERE id = NEW.membership_id;
      RETURN NEW; END $$""")
    op.execute("CREATE TRIGGER grants_auth_revision AFTER INSERT OR UPDATE OR DELETE ON membership_grants FOR EACH ROW EXECUTE FUNCTION bump_grant_authorization_revision()")


def downgrade():
    op.execute("DROP TRIGGER grants_auth_revision ON membership_grants")
    op.execute("DROP FUNCTION bump_grant_authorization_revision()")
    op.execute("DROP TRIGGER memberships_auth_revision ON store_memberships")
    op.execute("DROP FUNCTION bump_membership_authorization_revision()")
    op.execute("DROP TRIGGER users_auth_deactivation ON users")
    op.execute("DROP FUNCTION revoke_auth_sessions_on_deactivation()")
    for table in ("auth_rate_limits", "auth_audit", "membership_grants", "credential_tokens", "auth_sessions", "auth_accounts"):
        op.drop_table(table)
    op.drop_constraint("ck_store_memberships_authorization_revision", "store_memberships", type_="check")
    op.drop_column("store_memberships", "authorization_revision")
