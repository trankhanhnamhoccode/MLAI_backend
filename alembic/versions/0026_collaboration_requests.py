"""Add permission requests/audits and retained mapping submissions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0026_collaboration_requests"
down_revision = "0025_notifications_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("permission_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requester_membership_id", sa.Uuid(), sa.ForeignKey("store_memberships.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requester_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("facts", JSONB(), nullable=False), sa.Column("state", sa.String(16), nullable=False),
        sa.Column("version", sa.String(128), nullable=False), sa.Column("decision", JSONB()),
        sa.Column("approved_permissions", JSONB(), nullable=False), sa.Column("actually_added_permissions", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state IN ('pending','approved','rejected','cancelled','satisfied','invalidated')", name="ck_permission_request_state"))
    op.create_index("uq_permission_request_pending", "permission_requests", ["store_id", "requester_membership_id"], unique=True, postgresql_where=sa.text("state='pending'"))
    op.create_table("permission_request_audit", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), sa.ForeignKey("permission_requests.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("record", JSONB(), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("mapping_submissions", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("profile_id", sa.Uuid(), sa.ForeignKey("import_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("import_id", sa.Uuid(), sa.ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("submitted_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("facts", JSONB(), nullable=False), sa.Column("spec", JSONB(), nullable=False), sa.Column("evidence", JSONB(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False), sa.Column("version", sa.String(128), nullable=False),
        sa.Column("decision", JSONB()), sa.Column("reviewed_version", sa.String(128)),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state IN ('submitted','changes_requested','approved','rejected','stale','withdrawn')", name="ck_mapping_submission_state"))
    op.create_index("uq_mapping_submission_live", "mapping_submissions", ["profile_id"], unique=True, postgresql_where=sa.text("state='submitted'"))
    op.execute("""CREATE FUNCTION protect_collaboration_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP='DELETE' OR TG_TABLE_NAME='permission_request_audit' THEN
          RAISE EXCEPTION 'Collaboration audit requires retention';
        END IF;
        IF TG_TABLE_NAME='permission_requests' THEN
          IF (to_jsonb(OLD)-ARRAY['state','version','decision','approved_permissions','actually_added_permissions','updated_at'])
             IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['state','version','decision','approved_permissions','actually_added_permissions','updated_at']) THEN
            RAISE EXCEPTION 'Permission request facts are immutable';
          END IF;
          IF OLD.state<>'pending' AND to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
            RAISE EXCEPTION 'Terminal permission request is immutable';
          END IF;
        ELSE
          IF (to_jsonb(OLD)-ARRAY['state','version','decision','reviewed_version'])
             IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['state','version','decision','reviewed_version']) THEN
            RAISE EXCEPTION 'Mapping submission pins are immutable';
          END IF;
          IF OLD.state<>'submitted' AND to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
            RAISE EXCEPTION 'Terminal mapping submission is immutable';
          END IF;
        END IF;
        RETURN NEW;
      END $$""")
    for name in ("permission_requests", "permission_request_audit", "mapping_submissions"):
        op.execute(f"CREATE TRIGGER protect_{name} BEFORE UPDATE OR DELETE ON {name} FOR EACH ROW EXECUTE FUNCTION protect_collaboration_evidence()")


def downgrade():
    for name in ("permission_requests", "permission_request_audit", "mapping_submissions"):
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {name})")):
            raise RuntimeError("Collaboration evidence requires retention")
    for name in ("mapping_submissions", "permission_request_audit", "permission_requests"):
        op.drop_table(name)
    op.execute("DROP FUNCTION protect_collaboration_evidence()")
