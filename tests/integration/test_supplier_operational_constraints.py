"""S1.3 persistence/constraints on real isolated PostgreSQL; no application flows."""
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from alembic import command
import pytest
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from scripts.dev import migration_config

BASE_TABLES = {"users", "stores", "store_memberships", "products", "ingredients", "recipes", "recipe_lines"}
NEW_TABLES = {"suppliers", "supplier_terms", "sales_daily", "inventory_lots", "inventory_movements", "business_constraints"}
HEAD = "0006_forecast_decision_persist"


@pytest.fixture
def engine(database_settings: Settings) -> Iterator[Engine]:
    instance = create_database_engine(database_settings)
    try:
        yield instance
    finally:
        instance.dispose()


def parents(engine: Engine) -> dict[str, UUID]:
    from app.models import Ingredient, Product, Store, Supplier
    with Session(engine) as session:
        a, b = Store(name="Cafe"), Store(name="Cafe")
        session.add_all([a, b])
        session.flush()
        rows = {
            "store": a, "other_store": b,
            "supplier": Supplier(store_id=a.id, name="Local supplier"),
            "second_supplier": Supplier(store_id=a.id, name="Local supplier"),
            "other_supplier": Supplier(store_id=b.id, name="Local supplier"),
            "ingredient": Ingredient(store_id=a.id, name="Milk", base_unit="ml", expiry_tracking=True),
            "second_ingredient": Ingredient(store_id=a.id, name="Coffee", base_unit="g"),
            "other_ingredient": Ingredient(store_id=b.id, name="Milk", base_unit="ml"),
            "product": Product(store_id=a.id, name="Coffee", selling_unit="cup"),
            "other_product": Product(store_id=b.id, name="Coffee", selling_unit="cup"),
        }
        session.add_all(list(rows.values()))
        session.flush()
        ids = {key: row.id for key, row in rows.items()}
        session.commit()
    return ids


def term_values(ids: dict[str, UUID], **changes: object) -> dict[str, object]:
    values = dict(store_id=ids["store"], supplier_id=ids["supplier"], ingredient_id=ids["ingredient"],
                  unit="ml", version=1, effective_from=date(2026, 1, 1), effective_to=date(2026, 3, 31),
                  pack_size_base_quantity=Decimal("12000"), minimum_order_packs=2,
                  pack_cost=Decimal("360000"), lead_time_days=3, shelf_life_days=10)
    return values | changes


def lot_values(ids: dict[str, UUID], **changes: object) -> dict[str, object]:
    values = dict(store_id=ids["store"], ingredient_id=ids["ingredient"], supplier_id=ids["supplier"],
                  lot_code="MILK-20261001", received_date=date(2026, 10, 1), expiry_date=date(2026, 10, 7),
                  on_hand_quantity=Decimal("50"), unit="ml", unit_cost=Decimal("30"))
    return values | changes


def constraint_values(ids: dict[str, UUID], scope: str = "STORE", **changes: object) -> dict[str, object]:
    values = dict(store_id=ids["store"], scope_type=scope,
                  scope_id=None if scope == "STORE" else ids["ingredient"],
                  constraint_type="BUDGET_LIMIT" if scope == "STORE" else "MIN_SAFETY_STOCK",
                  numeric_value=Decimal("7000000") if scope == "STORE" else Decimal("10000"),
                  unit="VND" if scope == "STORE" else "ml", version=1,
                  effective_from=date(2026, 1, 1), effective_to=date(2026, 1, 31))
    return values | changes


def persisted_lot(engine: Engine, ids: dict[str, UUID]) -> UUID:
    from app.models import InventoryLot
    with Session(engine) as session:
        row = InventoryLot(**lot_values(ids))
        session.add(row)
        session.flush()
        identifier = row.id
        session.commit()
    return identifier


def test_fresh_schema_and_downgrade_reupgrade(engine: Engine) -> None:
    assert set(inspect(engine).get_table_names()) == BASE_TABLES | NEW_TABLES | {"alembic_version", "forecast_runs", "forecast_predictions", "decision_runs"}
    with engine.connect() as fresh:
        assert fresh.scalar(text("SELECT current_database()")) == "shelfcash_test"
        assert fresh.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
        exclusions = fresh.scalars(text("SELECT conname FROM pg_constraint WHERE contype='x'")).all()
        assert set(exclusions) == {"ex_recipes_product_period", "ex_supplier_terms_pair_period", "ex_business_constraints_scope_period"}
    command.downgrade(migration_config(), "0003_catalog_recipe")
    assert set(inspect(engine).get_table_names()) == BASE_TABLES | {"alembic_version"}
    command.upgrade(migration_config(), "head")
    assert set(inspect(engine).get_table_names()) == BASE_TABLES | NEW_TABLES | {"alembic_version", "forecast_runs", "forecast_predictions", "decision_runs"}


def test_six_models_commit_close_reload(engine: Engine) -> None:
    from app.models import BusinessConstraint, InventoryLot, InventoryMovement, SalesDaily, Supplier, SupplierTerm
    ids = parents(engine)
    lot_id = persisted_lot(engine, ids)
    occurred = datetime(2026, 10, 1, 9, tzinfo=timezone.utc)
    with Session(engine) as session:
        term = SupplierTerm(**term_values(ids))
        sale = SalesDaily(store_id=ids["store"], product_id=ids["product"], sales_date=date(2026, 10, 1), quantity=Decimal("10.125"))
        movement = InventoryMovement(store_id=ids["store"], lot_id=lot_id, ingredient_id=ids["ingredient"], movement_type="RECEIPT", quantity_delta=Decimal("50"), occurred_at=occurred, reference_type="schema_fixture", reference_id="receipt-001", note="Confirmed receipt fixture")
        budget = BusinessConstraint(**constraint_values(ids))
        safety = BusinessConstraint(**constraint_values(ids, "INGREDIENT"))
        rows = [term, sale, movement, budget, safety]
        session.add_all(rows)
        session.flush()
        identifiers = [row.id for row in rows]
        session.commit()
    with Session(engine) as fresh:
        supplier = fresh.get(Supplier, ids["supplier"])
        assert (supplier.store_id, supplier.name, supplier.active) == (ids["store"], "Local supplier", True)
        term = fresh.get(SupplierTerm, identifiers[0])
        for key, value in term_values(ids).items():
            assert getattr(term, key) == value
        assert term.active
        sale = fresh.get(SalesDaily, identifiers[1])
        assert (sale.store_id, sale.product_id, sale.sales_date, sale.quantity) == (ids["store"], ids["product"], date(2026, 10, 1), Decimal("10.125"))
        lot = fresh.get(InventoryLot, lot_id)
        for key, value in lot_values(ids).items():
            assert getattr(lot, key) == value
        movement = fresh.get(InventoryMovement, identifiers[2])
        assert (movement.store_id, movement.lot_id, movement.ingredient_id, movement.movement_type, movement.quantity_delta, movement.occurred_at, movement.reference_type, movement.reference_id, movement.note) == (ids["store"], lot_id, ids["ingredient"], "RECEIPT", Decimal("50"), occurred, "schema_fixture", "receipt-001", "Confirmed receipt fixture")
        for index, scope in [(3, "STORE"), (4, "INGREDIENT")]:
            row = fresh.get(BusinessConstraint, identifiers[index])
            for key, value in constraint_values(ids, scope).items():
                assert getattr(row, key) == value
            assert row.active
        for row in [supplier, term, sale, lot, movement, fresh.get(BusinessConstraint, identifiers[3])]:
            assert row.created_at.utcoffset() == timedelta(0)


def test_supplier_many_to_many_and_adjacent_versions(engine: Engine) -> None:
    from app.models import SupplierTerm
    ids = parents(engine)
    with Session(engine) as session:
        rows = [SupplierTerm(**term_values(ids)),
                SupplierTerm(**term_values(ids, version=2, effective_from=date(2026, 4, 1), effective_to=None)),
                SupplierTerm(**term_values(ids, supplier_id=ids["second_supplier"])),
                SupplierTerm(**term_values(ids, ingredient_id=ids["second_ingredient"], unit="g"))]
        session.add_all(rows)
        session.commit()
    with Session(engine) as fresh:
        assert len(fresh.scalars(select(SupplierTerm)).all()) == 4
        for day, expected in [(date(2025, 12, 31), []), (date(2026, 3, 31), [1]), (date(2026, 4, 1), [2]), (date(2099, 1, 1), [2])]:
            versions = fresh.scalars(select(SupplierTerm.version).where(SupplierTerm.supplier_id == ids["supplier"], SupplierTerm.ingredient_id == ids["ingredient"], SupplierTerm.active, SupplierTerm.effective_from <= day, (SupplierTerm.effective_to.is_(None) | (SupplierTerm.effective_to >= day)))).all()
            assert versions == expected


@pytest.mark.parametrize("field,value", [("pack_size_base_quantity", "0"), ("pack_size_base_quantity", "-1"), ("pack_size_base_quantity", "NaN"), ("minimum_order_packs", 0), ("pack_cost", "-1"), ("pack_cost", "Infinity"), ("lead_time_days", -1), ("shelf_life_days", -1), ("version", 0)])
def test_invalid_supplier_term_numbers(engine: Engine, field: str, value: object) -> None:
    from app.models import SupplierTerm
    ids = parents(engine)
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.add(SupplierTerm(**term_values(ids, **{field: value})))
        session.commit()


@pytest.mark.parametrize("issue", ["version", "overlap", "boundary", "period", "supplier_store", "ingredient_store", "unit", "missing_supplier", "missing_ingredient"])
def test_supplier_term_integrity(engine: Engine, issue: str) -> None:
    from app.models import SupplierTerm
    ids = parents(engine)
    values = term_values(ids)
    if issue in {"version", "overlap", "boundary"}:
        with Session(engine) as session:
            session.add(SupplierTerm(**values))
            session.commit()
        values.update(version=1 if issue == "version" else 2,
                      effective_from=date(2026, 4, 1) if issue == "version" else date(2026, 3, 31) if issue == "boundary" else date(2026, 3, 1), effective_to=None)
    elif issue == "period":
        values["effective_to"] = date(2025, 12, 31)
    else:
        key, value = {
            "supplier_store": ("supplier_id", ids["other_supplier"]),
            "ingredient_store": ("ingredient_id", ids["other_ingredient"]),
            "unit": ("unit", "L"), "missing_supplier": ("supplier_id", uuid4()),
            "missing_ingredient": ("ingredient_id", uuid4()),
        }[issue]
        values[key] = value
    with Session(engine) as session, pytest.raises(DBAPIError):
        session.add(SupplierTerm(**values))
        session.commit()


def test_inactive_term_overlap_allowed_but_activation_rejected(engine: Engine) -> None:
    from app.models import SupplierTerm
    ids = parents(engine)
    with Session(engine) as session:
        session.add(SupplierTerm(**term_values(ids)))
        inactive = SupplierTerm(**term_values(ids, version=2, active=False))
        session.add(inactive)
        session.flush()
        identifier = inactive.id
        session.commit()
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text("UPDATE supplier_terms SET active=true WHERE id=:id"), {"id": identifier})


@pytest.mark.parametrize("issue", ["duplicate", "negative", "nan", "cross_store", "missing_product"])
def test_canonical_sales_integrity(engine: Engine, issue: str) -> None:
    from app.models import SalesDaily
    ids = parents(engine)
    values = dict(store_id=ids["store"], product_id=ids["product"], sales_date=date(2026, 10, 1), quantity=Decimal("10"))
    if issue == "duplicate":
        with Session(engine) as session:
            session.add(SalesDaily(**values))
            session.commit()
        values["quantity"] = Decimal("105")
    elif issue in {"negative", "nan"}:
        values["quantity"] = Decimal("-1" if issue == "negative" else "NaN")
    else:
        values["product_id"] = ids["other_product"] if issue == "cross_store" else uuid4()
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.add(SalesDaily(**values))
        session.commit()
    if issue == "duplicate":
        with Session(engine) as fresh:
            assert fresh.scalar(select(SalesDaily.quantity)) == Decimal("10")


def test_same_sales_date_in_two_valid_store_contexts_and_zero_allowed(engine: Engine) -> None:
    from app.models import SalesDaily
    ids = parents(engine)
    with Session(engine) as session:
        session.add_all([SalesDaily(store_id=ids["store"], product_id=ids["product"], sales_date=date(2026, 10, 1), quantity=Decimal("0")), SalesDaily(store_id=ids["other_store"], product_id=ids["other_product"], sales_date=date(2026, 10, 1), quantity=Decimal("10"))])
        session.commit()
    with Session(engine) as fresh:
        assert sorted(fresh.scalars(select(SalesDaily.quantity)).all()) == [Decimal("0"), Decimal("10")]


@pytest.mark.parametrize("issue", ["negative", "infinity", "expiry", "unit", "ingredient_store", "supplier_store", "missing_ingredient", "missing_supplier", "cost"])
def test_lot_integrity(engine: Engine, issue: str) -> None:
    from app.models import InventoryLot
    ids = parents(engine)
    key, value = {
        "negative": ("on_hand_quantity", Decimal("-1")), "infinity": ("on_hand_quantity", Decimal("Infinity")),
        "expiry": ("expiry_date", date(2026, 9, 30)), "unit": ("unit", "L"),
        "ingredient_store": ("ingredient_id", ids["other_ingredient"]), "supplier_store": ("supplier_id", ids["other_supplier"]),
        "missing_ingredient": ("ingredient_id", uuid4()), "missing_supplier": ("supplier_id", uuid4()),
        "cost": ("unit_cost", Decimal("-1")),
    }[issue]
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.add(InventoryLot(**lot_values(ids, **{key: value})))
        session.commit()


def test_optional_lot_metadata_and_expiry_tracking_boundary(engine: Engine) -> None:
    from app.models import InventoryLot
    ids = parents(engine)
    with Session(engine) as session:
        row = InventoryLot(**lot_values(ids, supplier_id=None, lot_code=None, expiry_date=None, unit_cost=None, on_hand_quantity=Decimal("0")))
        session.add(row)
        session.flush()
        identifier = row.id
        session.commit()
    with Session(engine) as fresh:
        row = fresh.get(InventoryLot, identifier)
        assert row.on_hand_quantity == 0
        assert row.supplier_id is row.lot_code is row.expiry_date is row.unit_cost is None
    # This schema intentionally leaves tracked-ingredient mandatory expiry to a
    # future receipt boundary. No trigger/application validation is claimed.


@pytest.mark.parametrize("movement_type,delta", [("RECEIPT", "50"), ("USAGE", "-20"), ("WASTE", "-5"), ("EXPIRED", "-5"), ("COUNT_CORRECTION", "-1"), ("COUNT_CORRECTION", "1"), ("MANUAL_ADJUSTMENT", "2"), ("MANUAL_ADJUSTMENT", "-2")])
def test_movement_persistence_without_automatic_balance_update(engine: Engine, movement_type: str, delta: str) -> None:
    from app.models import InventoryLot, InventoryMovement
    ids = parents(engine)
    lot_id = persisted_lot(engine, ids)
    with Session(engine) as session:
        row = InventoryMovement(store_id=ids["store"], lot_id=lot_id, ingredient_id=ids["ingredient"], movement_type=movement_type, quantity_delta=Decimal(delta), occurred_at=datetime(2026, 10, 2, tzinfo=timezone.utc))
        session.add(row)
        session.flush()
        identifier = row.id
        session.commit()
    with Session(engine) as fresh:
        assert fresh.get(InventoryMovement, identifier).quantity_delta == Decimal(delta)
        assert fresh.get(InventoryLot, lot_id).on_hand_quantity == Decimal("50")


@pytest.mark.parametrize("issue", ["zero", "nan", "type", "receipt_sign", "usage_sign", "lot", "store", "ingredient", "missing_lot", "reference_pair"])
def test_movement_integrity(engine: Engine, issue: str) -> None:
    from app.models import InventoryMovement
    ids = parents(engine)
    lot_id = persisted_lot(engine, ids)
    values = dict(store_id=ids["store"], lot_id=lot_id, ingredient_id=ids["ingredient"], movement_type="RECEIPT", quantity_delta=Decimal("50"), occurred_at=datetime(2026, 10, 1, tzinfo=timezone.utc))
    key, value = {
        "zero": ("quantity_delta", Decimal("0")), "nan": ("quantity_delta", Decimal("NaN")),
        "type": ("movement_type", "RANDOM"), "receipt_sign": ("quantity_delta", Decimal("-1")),
        "usage_sign": ("movement_type", "USAGE"), "lot": ("lot_id", uuid4()),
        "store": ("store_id", ids["other_store"]), "ingredient": ("ingredient_id", ids["second_ingredient"]),
        "missing_lot": ("lot_id", uuid4()), "reference_pair": ("reference_type", "source"),
    }[issue]
    values[key] = value
    if issue == "lot":
        from app.models import InventoryLot
        with Session(engine) as session:
            other_lot = InventoryLot(**lot_values(ids, store_id=ids["other_store"], ingredient_id=ids["other_ingredient"], supplier_id=ids["other_supplier"]))
            session.add(other_lot)
            session.flush()
            values["lot_id"] = other_lot.id
            session.commit()
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.add(InventoryMovement(**values))
        session.commit()


@pytest.mark.parametrize("issue", ["store_id_present", "ingredient_id_missing", "type", "scope", "type_scope", "negative", "nan", "version", "period", "cross_store", "unit", "missing_ingredient"])
def test_business_constraint_integrity(engine: Engine, issue: str) -> None:
    from app.models import BusinessConstraint
    ids = parents(engine)
    scope = "INGREDIENT" if issue in {"ingredient_id_missing", "cross_store", "unit", "missing_ingredient"} else "STORE"
    key, value = {
        "store_id_present": ("scope_id", ids["ingredient"]), "ingredient_id_missing": ("scope_id", None),
        "type": ("constraint_type", "RANDOM_CONSTRAINT"), "scope": ("scope_type", "PRODUCT"),
        "type_scope": ("constraint_type", "MIN_SAFETY_STOCK"), "negative": ("numeric_value", Decimal("-1")),
        "nan": ("numeric_value", Decimal("NaN")), "version": ("version", 0),
        "period": ("effective_to", date(2025, 12, 31)), "cross_store": ("scope_id", ids["other_ingredient"]),
        "unit": ("unit", "L"), "missing_ingredient": ("scope_id", uuid4()),
    }[issue]
    with Session(engine) as session, pytest.raises(DBAPIError):
        session.add(BusinessConstraint(**constraint_values(ids, scope, **{key: value})))
        session.commit()


@pytest.mark.parametrize("scope", ["STORE", "INGREDIENT"])
@pytest.mark.parametrize("issue", ["version", "overlap", "boundary"])
def test_constraint_version_and_overlap(engine: Engine, scope: str, issue: str) -> None:
    from app.models import BusinessConstraint
    ids = parents(engine)
    with Session(engine) as session:
        session.add(BusinessConstraint(**constraint_values(ids, scope)))
        session.commit()
    changes = dict(version=1 if issue == "version" else 2, effective_from=date(2026, 2, 1) if issue == "version" else date(2026, 1, 31) if issue == "boundary" else date(2026, 1, 15), effective_to=None)
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.add(BusinessConstraint(**constraint_values(ids, scope, **changes)))
        session.commit()


@pytest.mark.parametrize("scope", ["STORE", "INGREDIENT"])
def test_adjacent_constraint_versions_and_inactive_activation(engine: Engine, scope: str) -> None:
    from app.models import BusinessConstraint
    ids = parents(engine)
    with Session(engine) as session:
        session.add_all([BusinessConstraint(**constraint_values(ids, scope)), BusinessConstraint(**constraint_values(ids, scope, version=2, effective_from=date(2026, 2, 1), effective_to=None, numeric_value=Decimal("8000000") if scope == "STORE" else Decimal("5000")))])
        inactive = BusinessConstraint(**constraint_values(ids, scope, version=3, active=False))
        session.add(inactive)
        session.flush()
        identifier = inactive.id
        session.commit()
    with Session(engine) as fresh:
        assert len(fresh.scalars(select(BusinessConstraint)).all()) == 3
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text("UPDATE business_constraints SET active=true WHERE id=:id"), {"id": identifier})


def test_reference_unit_and_audit_parent_changes_restricted(engine: Engine) -> None:
    from app.models import SupplierTerm, InventoryMovement
    ids = parents(engine)
    lot_id = persisted_lot(engine, ids)
    with Session(engine) as session:
        session.add_all([SupplierTerm(**term_values(ids)), InventoryMovement(store_id=ids["store"], lot_id=lot_id, ingredient_id=ids["ingredient"], movement_type="RECEIPT", quantity_delta=Decimal("50"), occurred_at=datetime(2026, 10, 1, tzinfo=timezone.utc))])
        session.commit()
    for statement, identifier in [("UPDATE ingredients SET base_unit='L' WHERE id=:id", ids["ingredient"]), ("DELETE FROM inventory_lots WHERE id=:id", lot_id)]:
        with engine.begin() as connection, pytest.raises(IntegrityError):
            connection.execute(text(statement), {"id": identifier})


def test_constraint_logical_keys_are_independent(engine: Engine) -> None:
    from app.models import BusinessConstraint
    ids = parents(engine)
    with Session(engine) as session:
        session.add_all([
            BusinessConstraint(**constraint_values(ids)),
            BusinessConstraint(**constraint_values(ids, store_id=ids["other_store"])),
            BusinessConstraint(**constraint_values(ids, "INGREDIENT")),
            BusinessConstraint(**constraint_values(ids, "INGREDIENT", scope_id=ids["second_ingredient"], unit="g")),
        ])
        session.commit()
    with Session(engine) as fresh:
        assert len(fresh.scalars(select(BusinessConstraint)).all()) == 4


def test_zero_cost_and_duration_boundaries(engine: Engine) -> None:
    from app.models import SupplierTerm, InventoryLot, BusinessConstraint
    ids = parents(engine)
    with Session(engine) as session:
        term = SupplierTerm(**term_values(ids, pack_size_base_quantity=Decimal("0.1234567890123456789"), minimum_order_packs=1, pack_cost=Decimal("0"), lead_time_days=0, shelf_life_days=0))
        lot = InventoryLot(**lot_values(ids, expiry_date=date(2026, 10, 1), on_hand_quantity=Decimal("0"), unit_cost=Decimal("0")))
        constraint = BusinessConstraint(**constraint_values(ids, numeric_value=Decimal("0"), effective_to=date(2026, 1, 1)))
        session.add_all([term, lot, constraint])
        session.flush()
        term_id, lot_id, constraint_id = term.id, lot.id, constraint.id
        session.commit()
    with Session(engine) as fresh:
        assert fresh.get(SupplierTerm, term_id).pack_size_base_quantity == Decimal("0.1234567890123456789")
        assert fresh.get(InventoryLot, lot_id).unit_cost == 0
        assert fresh.get(BusinessConstraint, constraint_id).numeric_value == 0


def test_expired_lot_remains_persisted_for_audit(engine: Engine) -> None:
    from app.models import InventoryLot
    ids = parents(engine)
    with Session(engine) as session:
        row = InventoryLot(**lot_values(ids, received_date=date(2026, 1, 1), expiry_date=date(2026, 1, 7)))
        session.add(row)
        session.flush()
        identifier = row.id
        session.commit()
    with Session(engine) as fresh:
        assert fresh.get(InventoryLot, identifier).expiry_date == date(2026, 1, 7)
        assert fresh.get(InventoryLot, identifier).on_hand_quantity == 50
    # Retention is storage behavior; future-demand usable quantity/FEFO is not computed.
