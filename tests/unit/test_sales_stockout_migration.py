"""Migration SQL/retention checks without a database connection."""
import importlib.util
from io import StringIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[2]


def load_migration():
    spec = importlib.util.spec_from_file_location(
        'stockout_migration', ROOT / 'alembic/versions/0019_sales_stockout.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_independent_revision_parent():
    migration = load_migration()
    assert migration.down_revision == '0017_planning_exports'
    assert migration.depends_on is None
    graph = ScriptDirectory(str(ROOT / 'alembic'))
    assert graph.get_revision(migration.revision).down_revision == migration.down_revision
    assert migration.revision in {r.revision for r in graph.walk_revisions(base='base', head='heads')}
    assert graph.get_heads() == ['0026_collaboration_requests']


def test_upgrade_only_adds_nullable_observation_without_default_or_backfill():
    migration = load_migration()
    output = StringIO()
    migration.op = Operations(MigrationContext.configure(
        dialect_name='postgresql', opts={'as_sql': True, 'output_buffer': output}
    ))
    migration.upgrade()
    assert output.getvalue().strip() == 'ALTER TABLE sales_daily ADD COLUMN is_stockout BOOLEAN;'


def test_downgrade_refuses_known_observations():
    migration = load_migration()
    migration.op = Mock()
    migration.op.get_bind.return_value.scalar.return_value = True
    with pytest.raises(RuntimeError, match='retained stockout observations'):
        migration.downgrade()
    query = migration.op.get_bind.return_value.scalar.call_args.args[0]
    assert 'WHERE is_stockout IS NOT NULL' in str(query)
    migration.op.drop_column.assert_not_called()


def test_downgrade_allows_only_unknown_observations():
    migration = load_migration()
    migration.op = Mock()
    migration.op.get_bind.return_value.scalar.return_value = False
    migration.downgrade()
    migration.op.drop_column.assert_called_once_with('sales_daily', 'is_stockout')
