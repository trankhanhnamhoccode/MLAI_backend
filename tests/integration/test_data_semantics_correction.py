"""Real PostgreSQL regressions; no import/readiness implementation is implied."""
from datetime import date
from decimal import Decimal

from alembic import command
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import InventoryLot, SupplierTerm
from scripts.dev import migration_config
from test_supplier_operational_constraints import engine, parents, lot_values, term_values


@pytest.mark.parametrize("insertion", ["orm_null", "sql_omitted", "sql_null"])
def test_unknown_receipt_persists_without_date_fallback(engine, insertion):
    ids = parents(engine)
    snapshot_date = date(2026, 10, 5)  # Source snapshot metadata, not receipt evidence.
    if insertion == "orm_null":
        with Session(engine) as session:
            row = InventoryLot(**lot_values(ids, received_date=None))
            session.add(row)
            session.flush()
            identifier = row.id
            session.commit()
    else:
        receipt_column = ", received_date" if insertion == "sql_null" else ""
        receipt_value = ", NULL" if insertion == "sql_null" else ""
        with engine.begin() as connection:
            identifier = connection.scalar(text(
                "INSERT INTO inventory_lots (store_id, ingredient_id, on_hand_quantity, unit, expiry_date"
                + receipt_column + ") VALUES (:store, :ingredient, 50, 'ml', '2026-10-07'"
                + receipt_value + ") RETURNING id"
            ), {"store": ids["store"], "ingredient": ids["ingredient"]})
    with Session(engine) as fresh:
        row = fresh.get(InventoryLot, identifier)
        assert row.received_date is None
        assert row.received_date != snapshot_date
        assert row.on_hand_quantity == Decimal("50")
        assert row.expiry_date == date(2026, 10, 7)
        assert row.unit == "ml"
    column = next(c for c in inspect(engine).get_columns("inventory_lots") if c["name"] == "received_date")
    assert column["nullable"] and column["default"] is None


@pytest.mark.parametrize("field", ["effective_from", "lead_time_days", "pack_cost"])
def test_missing_strict_supplier_input_rejected_without_default(engine, field):
    ids = parents(engine)
    column = next(c for c in inspect(engine).get_columns("supplier_terms") if c["name"] == field)
    assert not column["nullable"] and column["default"] is None
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.add(SupplierTerm(**term_values(ids, **{field: None})))
        session.commit()


def test_canonical_pack_cost_exact_fresh_reload(engine):
    # Known canonical fixture: 15 kg * 28,000 VND/kg = 420,000 VND/pack.
    # This tests storage meaning; no source normalization engine exists.
    ids = parents(engine)
    with Session(engine) as session:
        row = SupplierTerm(**term_values(ids, ingredient_id=ids["second_ingredient"],
                            unit="g", pack_size_base_quantity=Decimal("15000"),
                            pack_cost=Decimal("420000")))
        session.add(row)
        session.flush()
        identifier = row.id
        session.commit()
    with Session(engine) as fresh:
        row = fresh.get(SupplierTerm, identifier)
        assert row.pack_size_base_quantity == Decimal("15000")
        assert row.unit == "g"
        assert row.pack_cost == Decimal("420000")
        assert row.pack_cost != Decimal("28000")


def test_migration_downgrade_reupgrade_preserves_known_receipt(engine):
    ids = parents(engine)
    with Session(engine) as session:
        row = InventoryLot(**lot_values(ids))
        session.add(row)
        session.flush()
        identifier = row.id
        session.commit()
    tables = set(inspect(engine).get_table_names())
    command.downgrade(migration_config(), "0004_supplier_ops_constraints")
    assert not next(c for c in inspect(engine).get_columns("inventory_lots") if c["name"] == "received_date")["nullable"]
    command.upgrade(migration_config(), "head")
    assert set(inspect(engine).get_table_names()) == tables
    with Session(engine) as fresh:
        assert fresh.get(InventoryLot, identifier).received_date == date(2026, 10, 1)
    with engine.connect() as fresh:
        assert fresh.scalar(text("SELECT version_num FROM alembic_version")) == "0005_data_semantics_correction"


def test_downgrade_refuses_unknown_receipt_without_fabrication(engine):
    ids = parents(engine)
    with Session(engine) as session:
        row = InventoryLot(**lot_values(ids, received_date=None))
        session.add(row)
        session.flush()
        identifier = row.id
        session.commit()
    with pytest.raises(IntegrityError):
        command.downgrade(migration_config(), "0004_supplier_ops_constraints")
    with Session(engine) as fresh:
        assert fresh.get(InventoryLot, identifier).received_date is None
    with engine.connect() as fresh:
        assert fresh.scalar(text("SELECT version_num FROM alembic_version")) == "0005_data_semantics_correction"
