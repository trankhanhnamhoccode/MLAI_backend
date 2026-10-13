"""S4.2 additive Staff/invitation/audit/receipt/delivery storage; no backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_staff_invitations"
down_revision = "0010_auth_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('staff_invitations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('store_id', sa.UUID(), nullable=False),
    sa.Column('target_email', sa.String(length=320), nullable=False),
    sa.Column('issuer_user_id', sa.UUID(), nullable=False),
    sa.Column('version', sa.String(length=128), nullable=False),
    sa.Column('token_digest', sa.String(length=64), nullable=False),
    sa.Column('offered_grants', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('permission_catalog_version', sa.String(length=128), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reason', sa.String(length=1000), nullable=False),
    sa.Column('delivery_status', sa.String(length=16), nullable=False),
    sa.CheckConstraint("jsonb_typeof(offered_grants) = 'array'", name='ck_staff_invitations_grants'),
    sa.CheckConstraint("status IN ('pending','accepted','revoked','expired')", name='ck_staff_invitations_status'),
    sa.ForeignKeyConstraint(['issuer_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_staff_invitations_store_id'), 'staff_invitations', ['store_id'], unique=False)
    op.create_index('uq_staff_invitations_pending', 'staff_invitations', ['store_id', 'target_email'], unique=True, postgresql_where=sa.text("status = 'pending'"))
    op.create_table('permission_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('store_id', sa.UUID(), nullable=False),
    sa.Column('membership_id', sa.UUID(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('record_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.ForeignKeyConstraint(['membership_id'], ['store_memberships.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_permission_events_store_id'), 'permission_events', ['store_id'], unique=False)
    op.create_table('invitation_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('store_id', sa.UUID(), nullable=False),
    sa.Column('invitation_id', sa.Uuid(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('record_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.ForeignKeyConstraint(['invitation_id'], ['staff_invitations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invitation_events_store_id'), 'invitation_events', ['store_id'], unique=False)
    op.create_table('staff_request_receipts',
    sa.Column('actor_id', sa.UUID(), nullable=False),
    sa.Column('store_id', sa.UUID(), nullable=False),
    sa.Column('operation', sa.String(length=200), nullable=False),
    sa.Column('key_digest', sa.String(length=64), nullable=False),
    sa.Column('request_digest', sa.String(length=64), nullable=False),
    sa.Column('record_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('actor_id', 'store_id', 'operation', 'key_digest')
    )
    op.create_table('invitation_delivery_intents',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('invitation_id', sa.Uuid(), nullable=False),
    sa.Column('invitation_version', sa.String(length=128), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('claim', sa.Uuid(), nullable=True),
    sa.Column('ciphertext', sa.LargeBinary(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('queued','delivered','failed')", name='ck_invitation_delivery_status'),
    sa.ForeignKeyConstraint(['invitation_id'], ['staff_invitations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invitation_delivery_intents_invitation_id'), 'invitation_delivery_intents', ['invitation_id'], unique=False)

    op.execute("""CREATE FUNCTION reject_staff_history_mutation() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Staff history is append-only' USING ERRCODE = '23514'; END $$""")
    for table in ("permission_events", "invitation_events", "staff_request_receipts"):
        op.execute(f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_staff_history_mutation()")


def downgrade():
    for table in ("invitation_delivery_intents", "staff_request_receipts", "invitation_events", "permission_events", "staff_invitations"):
        op.drop_table(table)
    op.execute("DROP FUNCTION reject_staff_history_mutation()")
