"""Allow explicit test challenger metadata/2; preserve every existing payload."""
from alembic import op
import sqlalchemy as sa

revision='f4_20261016_metadata_v2'
down_revision='0027_self_service_stores'
branch_labels=None
depends_on=None


def constraint(versions):
    op.drop_constraint('ck_forecast_execution_metadata_version','forecast_execution_metadata',type_='check')
    op.create_check_constraint('ck_forecast_execution_metadata_version','forecast_execution_metadata',
        "details_json ? 'schema_version' AND jsonb_typeof(details_json->'schema_version') = 'number' "
        f"AND details_json->>'schema_version' IN ({versions})")


def upgrade():
    constraint("'1','2'")


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM forecast_execution_metadata WHERE details_json->>'schema_version'!='1')")):
        raise RuntimeError('Retain metadata/2 history; downgrade requires an explicit preservation plan')
    constraint("'1'")
