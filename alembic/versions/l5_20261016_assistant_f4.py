"""Join independent Assistant and forecast metadata heads without changing history."""

revision = 'l5_20261016_assistant_f4'
down_revision = ('0030_conversational_chat', 'f4_20261016_metadata_v2')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    # Parent migrations retain their evidence-preserving downgrade guards.
    pass
