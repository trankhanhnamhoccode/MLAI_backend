"""A1 additive migration preserves observed sales and guards observation loss."""
from datetime import date
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.infrastructure.database.engine import create_database_engine
from app.models import Product, SalesDaily, Store
from scripts.dev import migration_config


def test_upgrade_existing_sales_nullable_and_downgrade_retention_guard(database_settings):
    engine = create_database_engine(database_settings)
    store, product, sale = uuid4(), uuid4(), uuid4()
    try:
        command.downgrade(migration_config(), '0017_planning_exports')
        with Session(engine) as writer, writer.begin():
            writer.add(Store(id=store, name='Synthetic migration'))
            writer.flush()
            writer.add(Product(id=product, store_id=store, name='Synthetic', selling_unit='cup'))
            writer.flush()
            writer.execute(text('INSERT INTO sales_daily (id, store_id, product_id, sales_date, quantity) '
                'VALUES (:id, :store, :product, :day, :quantity)'),
                dict(id=sale, store=store, product=product, day=date(2026, 10, 9), quantity=100))
        command.upgrade(migration_config(), '0019_sales_stockout')
        with Session(engine) as fresh:
            row = fresh.get(SalesDaily, sale)
            assert row.quantity == 100 and row.is_stockout is None
        column = next(c for c in inspect(engine).get_columns('sales_daily') if c['name'] == 'is_stockout')
        assert column['nullable'] and column['default'] is None
        with Session(engine) as writer, writer.begin():
            writer.get(SalesDaily, sale).is_stockout = False
        with pytest.raises(RuntimeError, match='retained stockout observations'):
            command.downgrade(migration_config(), '0017_planning_exports')
        with Session(engine) as fresh:
            assert fresh.get(SalesDaily, sale).is_stockout is False
            assert fresh.scalar(text('SELECT version_num FROM alembic_version')) == '0019_sales_stockout'
    finally:
        engine.dispose()
