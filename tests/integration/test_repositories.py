"""S1.5 access contracts on isolated PostgreSQL; fixtures are not engine output."""
from collections.abc import Iterator
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from app.models import (
    BusinessConstraint, DecisionRun, ForecastPrediction, ForecastRun, Ingredient,
    InventoryLot, InventoryMovement, Product, Recipe, RecipeLine, SalesDaily,
    Store, StoreMembership, Supplier, SupplierTerm, User,
)
from app.repositories.catalog import CatalogRepository
from app.repositories.constraints import ConstraintsRepository
from app.repositories.decision import DecisionRepository
from app.repositories.forecast import ForecastRepository
from app.repositories.identity import IdentityRepository, StoreRepository
from app.repositories.inventory import InventoryRepository
from app.repositories.recipe import RecipeRepository
from app.repositories.sales import SalesRepository
from app.repositories.supplier import SupplierRepository

DAY = date(2026, 10, 1)
END = date(2026, 10, 7)
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)

INSERTS = [
    (IdentityRepository, "add_membership", StoreMembership, "membership"),
    (CatalogRepository, "add_product", Product, "product"),
    (CatalogRepository, "add_ingredient", Ingredient, "ingredient"),
    (RecipeRepository, "add_recipe", Recipe, "recipe"),
    (RecipeRepository, "add_recipe_line", RecipeLine, "line"),
    (SupplierRepository, "add_supplier", Supplier, "supplier"),
    (SupplierRepository, "add_supplier_term", SupplierTerm, "term"),
    (SalesRepository, "add_sales_record", SalesDaily, "sale"),
    (InventoryRepository, "add_lot", InventoryLot, "lot"),
    (InventoryRepository, "append_movement", InventoryMovement, "movement"),
    (ConstraintsRepository, "add_constraint", BusinessConstraint, "budget"),
    (ForecastRepository, "add_forecast_run", ForecastRun, "forecast"),
    (DecisionRepository, "add_decision_run", DecisionRun, "decision"),
]


def uid(number: int) -> UUID:
    return UUID(int=number)


@pytest.fixture
def engine(database_settings: Settings) -> Iterator[Engine]:
    instance = create_database_engine(database_settings)
    try:
        yield instance
    finally:
        instance.dispose()


def forecast(store: UUID, identifier: UUID) -> ForecastRun:
    return ForecastRun(
        id=identifier, store_id=store, status="COMPLETED",
        training_start_date=date(2026, 9, 1), training_end_date=date(2026, 9, 30),
        forecast_start_date=DAY, forecast_end_date=END, model_type="access_fixture",
        model_version="fixture-v1", input_fingerprint="same-input",
        metrics_json={"MAE": "2.125"}, started_at=NOW, completed_at=NOW,
    )


def decision(store: UUID, run: UUID, identifier: UUID) -> DecisionRun:
    return DecisionRun(
        id=identifier, store_id=store, forecast_run_id=run, status="COMPLETED",
        planning_start_date=DAY, planning_end_date=END, package_schema_version=1,
        input_fingerprint="same-input", input_snapshot_json={"stock": "50.125"},
        decision_package_json={"fixture_only": True, "recommendation": "BALANCED"},
        recommended_strategy="BALANCED", started_at=NOW, completed_at=NOW,
    )


@pytest.fixture
def graph(engine: Engine) -> dict[int, dict[str, UUID]]:
    """Write all 16 tables through repositories, explicitly flush dependency groups."""
    ids = {}
    with Session(engine) as session, session.begin():
        IdentityRepository(session).add_user(User(
            id=uid(1), email="owner@example.test", password_hash="opaque-fixture",
            display_name="Owner"))
        for base in (100, 200):
            store = uid(base)
            rows = {name: uid(base + offset) for offset, name in enumerate(
                ("product", "ingredient", "recipe", "line", "supplier", "term",
                 "sale", "lot", "movement", "budget", "forecast", "prediction",
                 "decision", "membership"), start=1)}
            ids[base] = {"store": store, **rows}
            StoreRepository(session).add_store(Store(id=store, name="Cafe"))
            session.flush()
            IdentityRepository(session).add_membership(store, StoreMembership(
                id=rows["membership"], store_id=store, user_id=uid(1), role="OWNER"))
            catalog = CatalogRepository(session)
            catalog.add_product(store, Product(
                id=rows["product"], store_id=store, sku="COFFEE", name="Coffee",
                selling_unit="cup", price=Decimal("25000.125"), active=False))
            catalog.add_ingredient(store, Ingredient(
                id=rows["ingredient"], store_id=store, sku="MILK", name="Milk",
                base_unit="ml", active=False))
            supplier = SupplierRepository(session)
            supplier.add_supplier(store, Supplier(
                id=rows["supplier"], store_id=store, name="Supplier"))
            session.flush()
            recipes = RecipeRepository(session)
            recipes.add_recipe(store, Recipe(
                id=rows["recipe"], store_id=store, product_id=rows["product"],
                version=1, effective_from=DAY, effective_to=END,
                yield_quantity=Decimal("10")))
            supplier.add_supplier_term(store, SupplierTerm(
                id=rows["term"], store_id=store, supplier_id=rows["supplier"],
                ingredient_id=rows["ingredient"], unit="ml", version=1,
                effective_from=DAY, effective_to=END, pack_size_base_quantity=Decimal("15000"),
                minimum_order_packs=1, pack_cost=Decimal("420000"), lead_time_days=3))
            SalesRepository(session).add_sales_record(store, SalesDaily(
                id=rows["sale"], store_id=store, product_id=rows["product"],
                sales_date=DAY, quantity=Decimal("10.125")))
            inventory = InventoryRepository(session)
            inventory.add_lot(store, InventoryLot(
                id=rows["lot"], store_id=store, ingredient_id=rows["ingredient"],
                on_hand_quantity=Decimal("50.125"), unit="ml", received_date=None,
                expiry_date=END))
            ConstraintsRepository(session).add_constraint(store, BusinessConstraint(
                id=rows["budget"], store_id=store, scope_type="STORE", scope_id=None,
                constraint_type="BUDGET_LIMIT", numeric_value=Decimal("7000000"),
                unit="VND", version=1, effective_from=DAY, effective_to=END))
            session.flush()
            recipes.add_recipe_line(store, RecipeLine(
                id=rows["line"], store_id=store, recipe_id=rows["recipe"],
                ingredient_id=rows["ingredient"], quantity=Decimal("800.125"), unit="ml"))
            inventory.append_movement(store, InventoryMovement(
                id=rows["movement"], store_id=store, lot_id=rows["lot"],
                ingredient_id=rows["ingredient"], movement_type="RECEIPT",
                quantity_delta=Decimal("50.125"), occurred_at=NOW, note="Fixture receipt"))
            ForecastRepository(session).add_forecast_run(store, forecast(store, rows["forecast"]), [
                ForecastPrediction(id=rows["prediction"], store_id=store,
                    forecast_run_id=rows["forecast"], product_id=rows["product"],
                    forecast_date=DAY, p25=Decimal("80"), p50=Decimal("100.125"), p75=Decimal("130"))
            ])
            DecisionRepository(session).add_decision_run(
                store, decision(store, rows["forecast"], rows["decision"]))
    return ids


def test_all_tables_round_trip_through_fresh_repositories(engine: Engine, graph) -> None:
    a = graph[100]
    with Session(engine) as fresh:
        identity, stores = IdentityRepository(fresh), StoreRepository(fresh)
        assert identity.get_user_by_id(uid(1)).email == "owner@example.test"
        assert identity.get_user_by_email("owner@example.test").id == uid(1)
        assert identity.get_user_by_email("Owner@example.test") is None
        assert stores.get_store_by_id(a["store"]).currency == "VND"
        assert identity.get_membership(a["store"], uid(1)).id == a["membership"]
        assert [r.id for r in identity.list_memberships_for_store(a["store"])] == [a["membership"]]
        c = CatalogRepository(fresh)
        assert c.get_product(a["store"], a["product"]).price == Decimal("25000.125")
        assert c.get_product_by_sku(a["store"], "COFFEE").id == a["product"]
        assert c.get_ingredient_by_sku(a["store"], "MILK").id == a["ingredient"]
        assert [r.id for r in c.list_products(a["store"])] == [a["product"]]
        assert [r.id for r in c.list_ingredients(a["store"])] == [a["ingredient"]]
        recipes = RecipeRepository(fresh)
        assert recipes.get_recipe(a["store"], a["recipe"]).version == 1
        assert recipes.list_recipe_lines(a["store"], a["recipe"])[0].quantity == Decimal("800.125")
        supplier = SupplierRepository(fresh)
        assert supplier.get_supplier(a["store"], a["supplier"]).name == "Supplier"
        assert [r.id for r in supplier.list_suppliers(a["store"])] == [a["supplier"]]
        assert supplier.get_supplier_term(a["store"], a["term"]).pack_cost == Decimal("420000")
        assert [r.id for r in supplier.list_supplier_terms(a["store"], a["ingredient"])] == [a["term"]]
        assert SalesRepository(fresh).get_daily_sale(a["store"], a["product"], DAY).quantity == Decimal("10.125")
        inventory = InventoryRepository(fresh)
        assert inventory.get_lot(a["store"], a["lot"]).received_date is None
        assert [r.id for r in inventory.list_lots(a["store"], a["ingredient"])] == [a["lot"]]
        assert inventory.list_movements(a["store"], a["lot"])[0].quantity_delta == Decimal("50.125")
        assert ConstraintsRepository(fresh).get_constraint(a["store"], a["budget"]).scope_id is None
        forecast_repo = ForecastRepository(fresh)
        assert forecast_repo.get_forecast_run(a["store"], a["forecast"]).metrics_json == {"MAE": "2.125"}
        assert [r.id for r in forecast_repo.list_forecast_runs(a["store"])] == [a["forecast"]]
        assert forecast_repo.list_predictions(a["store"], a["forecast"])[0].p50 == Decimal("100.125")
        decisions = DecisionRepository(fresh)
        assert decisions.get_decision_run(a["store"], a["decision"]).input_snapshot_json == {"stock": "50.125"}
        assert [r.id for r in decisions.list_decision_runs(a["store"])] == [a["decision"]]


@pytest.mark.parametrize("repository,method,key", [
    (CatalogRepository, "get_product", "product"),
    (CatalogRepository, "get_ingredient", "ingredient"),
    (RecipeRepository, "get_recipe", "recipe"),
    (SupplierRepository, "get_supplier", "supplier"),
    (SupplierRepository, "get_supplier_term", "term"),
    (InventoryRepository, "get_lot", "lot"),
    (InventoryRepository, "get_lot_for_update", "lot"),
    (ConstraintsRepository, "get_constraint", "budget"),
    (ForecastRepository, "get_forecast_run", "forecast"),
    (DecisionRepository, "get_decision_run", "decision"),
])
def test_scoped_get_even_with_other_store_in_identity_map(engine, graph, repository, method, key):
    a, b = graph[100], graph[200]
    with Session(engine) as session:
        get = getattr(repository(session), method)
        assert get(b["store"], b[key]) is not None
        assert get(a["store"], b[key]) is None
        assert get(a["store"], uuid4()) is None


def test_all_related_lists_and_business_lookups_are_store_scoped(engine, graph):
    a, b = graph[100], graph[200]
    with Session(engine) as s:
        c = CatalogRepository(s)
        assert c.get_product_by_sku(a["store"], "COFFEE").id == a["product"]
        assert c.get_ingredient_by_sku(a["store"], "MILK").id == a["ingredient"]
        assert RecipeRepository(s).list_recipe_versions(a["store"], b["product"]) == []
        assert RecipeRepository(s).get_active_recipe(a["store"], b["product"], DAY) is None
        assert RecipeRepository(s).list_recipe_lines(a["store"], b["recipe"]) == []
        assert SupplierRepository(s).list_supplier_terms(a["store"], b["ingredient"]) == []
        assert SupplierRepository(s).list_active_supplier_terms(a["store"], b["ingredient"], DAY) == []
        assert SalesRepository(s).get_daily_sale(a["store"], b["product"], DAY) is None
        assert SalesRepository(s).get_sales_history(a["store"], b["product"], DAY, END) == []
        assert {r.store_id for r in SalesRepository(s).list_store_sales(a["store"], DAY, END)} == {a["store"]}
        assert InventoryRepository(s).list_lots(a["store"], b["ingredient"]) == []
        assert InventoryRepository(s).list_movements(a["store"], b["lot"]) == []
        assert ForecastRepository(s).list_predictions(a["store"], b["forecast"]) == []
        assert IdentityRepository(s).get_membership(a["store"], uuid4()) is None
        assert {r.store_id for r in ConstraintsRepository(s).list_constraints(a["store"])} == {a["store"]}
        assert {r.store_id for r in ConstraintsRepository(s).list_active_constraints(a["store"], DAY)} == {a["store"]}


def test_effective_dates_versions_inactive_and_open_ends(engine, graph):
    a = graph[100]
    next_day = date(2026, 10, 8)
    with Session(engine) as s, s.begin():
        RecipeRepository(s).add_recipe(a["store"], Recipe(store_id=a["store"],
            product_id=a["product"], version=2, effective_from=next_day, yield_quantity=Decimal("10")))
        old_term = SupplierRepository(s).get_supplier_term(a["store"], a["term"])
        values = {name: getattr(old_term, name) for name in (
            "store_id", "supplier_id", "ingredient_id", "unit", "pack_size_base_quantity",
            "minimum_order_packs", "pack_cost", "lead_time_days")}
        SupplierRepository(s).add_supplier_term(a["store"], SupplierTerm(
            **values, version=2, effective_from=next_day))
        SupplierRepository(s).add_supplier_term(a["store"], SupplierTerm(
            **values, version=3, effective_from=DAY, active=False))
        for version, start, active in [(2, next_day, True), (3, DAY, False)]:
            ConstraintsRepository(s).add_constraint(a["store"], BusinessConstraint(
                store_id=a["store"], scope_type="STORE", constraint_type="BUDGET_LIMIT",
                numeric_value=Decimal("8000000"), unit="VND", version=version,
                effective_from=start, active=active))
    with Session(engine) as fresh:
        recipes, suppliers, constraints = RecipeRepository(fresh), SupplierRepository(fresh), ConstraintsRepository(fresh)
        for day, expected in [(date(2026, 9, 30), None), (DAY, 1), (END, 1), (next_day, 2), (date(2099, 1, 1), 2)]:
            recipe = recipes.get_active_recipe(a["store"], a["product"], day)
            assert (recipe.version if recipe else None) == expected
            versions = [] if expected is None else [expected]
            assert [r.version for r in suppliers.list_active_supplier_terms(a["store"], a["ingredient"], day)] == versions
            assert [r.version for r in constraints.list_active_constraints(a["store"], day)] == versions
        assert [r.version for r in recipes.list_recipe_versions(a["store"], a["product"])] == [1, 2]
        assert [r.version for r in suppliers.list_supplier_terms(a["store"], a["ingredient"])] == [1, 2, 3]
        assert [r.version for r in constraints.list_constraints(a["store"])] == [1, 2, 3]


def test_sales_inclusive_chronological_missing_and_duplicate(engine, graph):
    a = graph[100]
    with Session(engine) as s, s.begin():
        repo = SalesRepository(s)
        for day in (END, date(2026, 9, 30), date(2026, 10, 4)):
            repo.add_sales_record(a["store"], SalesDaily(store_id=a["store"],
                product_id=a["product"], sales_date=day, quantity=Decimal("0")))
    with Session(engine) as fresh:
        repo = SalesRepository(fresh)
        expected = [DAY, date(2026, 10, 4), END]
        assert [r.sales_date for r in repo.get_sales_history(a["store"], a["product"], DAY, END)] == expected
        assert [r.sales_date for r in repo.list_store_sales(a["store"], DAY, END)] == expected
        assert repo.get_daily_sale(a["store"], a["product"], date(2026, 10, 2)) is None
        with pytest.raises(ValueError):
            repo.get_sales_history(a["store"], a["product"], END, DAY)
        with pytest.raises(ValueError):
            repo.list_store_sales(a["store"], END, DAY)
    with Session(engine) as s, pytest.raises(IntegrityError):
        with s.begin():
            SalesRepository(s).add_sales_record(a["store"], SalesDaily(
                store_id=a["store"], product_id=a["product"], sales_date=DAY, quantity=Decimal("105")))
    with Session(engine) as fresh:
        assert SalesRepository(fresh).get_daily_sale(a["store"], a["product"], DAY).quantity == Decimal("10.125")


def test_shared_transaction_flush_is_not_commit_and_explicit_rollback(engine, graph):
    a = graph[100]
    product_id, supplier_id = uuid4(), uuid4()
    with Session(engine) as s:
        CatalogRepository(s).add_product(a["store"], Product(
            id=product_id, store_id=a["store"], name="Rollback", selling_unit="cup"))
        SupplierRepository(s).add_supplier(a["store"], Supplier(
            id=supplier_id, store_id=a["store"], name="Rollback"))
        s.flush()
        with Session(engine) as observer:
            assert CatalogRepository(observer).get_product(a["store"], product_id) is None
            assert SupplierRepository(observer).get_supplier(a["store"], supplier_id) is None
        s.rollback()
    with Session(engine) as fresh:
        assert CatalogRepository(fresh).get_product(a["store"], product_id) is None
        assert SupplierRepository(fresh).get_supplier(a["store"], supplier_id) is None


@pytest.mark.parametrize("valid", [True, False])
def test_inventory_caller_transaction_atomicity_on_movement_failure(engine, graph, valid):
    a = graph[100]
    with Session(engine) as s:
        try:
            with s.begin():
                repo = InventoryRepository(s)
                lot = repo.get_lot_for_update(a["store"], a["lot"])
                lot.on_hand_quantity = Decimal("30.125")  # Fixture caller, not mutation service.
                s.flush()
                repo.append_movement(a["store"], InventoryMovement(
                    store_id=a["store"], lot_id=a["lot"], ingredient_id=a["ingredient"],
                    movement_type="USAGE", quantity_delta=Decimal("-20") if valid else Decimal("20"),
                    occurred_at=NOW, note="Fixture use"))
        except IntegrityError:
            assert not valid
        else:
            assert valid
    with Session(engine) as fresh:
        repo = InventoryRepository(fresh)
        assert repo.get_lot(a["store"], a["lot"]).on_hand_quantity == Decimal("30.125" if valid else "50.125")
        assert len(repo.list_movements(a["store"], a["lot"])) == (2 if valid else 1)


def test_cross_store_related_insert_rejected_by_fk(engine, graph):
    a, b = graph[100], graph[200]
    with Session(engine) as s, pytest.raises(IntegrityError):
        with s.begin():
            RecipeRepository(s).add_recipe(a["store"], Recipe(
                store_id=a["store"], product_id=b["product"], version=2,
                effective_from=date(2026, 10, 8), yield_quantity=Decimal("1")))
    with Session(engine) as fresh:
        assert len(RecipeRepository(fresh).list_recipe_versions(a["store"], a["product"])) == 1


def test_run_reruns_generated_ids_and_snapshot_independence(engine, graph):
    a = graph[100]
    with Session(engine) as s, s.begin():
        run = forecast(a["store"], uuid4())
        run.id = None  # Exercise actual database-generated identity.
        prediction = ForecastPrediction(store_id=a["store"], product_id=a["product"],
            forecast_date=DAY, p25=Decimal("0"), p50=Decimal("0"), p75=Decimal("0"))
        ForecastRepository(s).add_forecast_run(a["store"], run, [prediction])
        run_id = run.id
        row = decision(a["store"], run_id, uuid4())
        expected = deepcopy(row.input_snapshot_json)
        DecisionRepository(s).add_decision_run(a["store"], row)
        row_id = row.id
    with Session(engine) as fresh:
        assert run_id != a["forecast"]
        assert len(ForecastRepository(fresh).list_forecast_runs(a["store"])) == 2
        assert ForecastRepository(fresh).list_predictions(a["store"], run_id)[0].p50 == Decimal("0")
        assert DecisionRepository(fresh).get_decision_run(a["store"], row_id).input_snapshot_json == expected
        assert len(DecisionRepository(fresh).list_decision_runs(a["store"])) == 2


@pytest.mark.parametrize("repository,method,model,key", INSERTS)
def test_inserts_cannot_readd_existing_or_detached_rows(engine, graph, repository, method, model, key):
    a = graph[100]
    with Session(engine) as s:
        row = s.get(model, a[key])
        insert = getattr(repository(s), method)
        with pytest.raises(ValueError, match="transient"):
            insert(a["store"], row)
        s.expunge(row)
        with pytest.raises(ValueError, match="transient"):
            insert(a["store"], row)
        assert not s.new


def test_forecast_aggregate_validation_before_staging_and_rollback(engine, graph):
    a, b = graph[100], graph[200]
    with Session(engine) as s:
        repo = ForecastRepository(s)
        run = forecast(a["store"], uuid4())
        prediction = ForecastPrediction(store_id=b["store"], product_id=b["product"])
        with pytest.raises(ValueError, match="Store"):
            repo.add_forecast_run(a["store"], run, [prediction])
        assert not s.new
        prediction.store_id = a["store"]
        prediction.forecast_run_id = b["forecast"]
        with pytest.raises(ValueError, match="ForecastRun"):
            repo.add_forecast_run(a["store"], run, [prediction])
        assert not s.new
        repo.add_forecast_run(a["store"], run)
        with Session(engine) as observer:
            assert ForecastRepository(observer).get_forecast_run(a["store"], run.id) is None
        s.rollback()
    with Session(engine) as fresh:
        assert len(ForecastRepository(fresh).list_forecast_runs(a["store"])) == 1


@pytest.mark.parametrize("repository,method,model,key", INSERTS)
def test_wrong_store_insert_is_rejected_before_staging(engine, repository, method, model, key):
    with Session(engine) as s:
        with pytest.raises(ValueError, match="Store"):
            getattr(repository(s), method)(uid(100), model(store_id=uid(200)))
        assert not s.new


def test_inventory_lock_refreshes_cached_balance_and_last_until_caller_rollback(engine, graph):
    a = graph[100]
    with Session(engine) as owner, Session(engine) as competitor:
        repo = InventoryRepository(owner)
        cached = repo.get_lot(a["store"], a["lot"])
        with engine.begin() as writer:
            # Privileged fixture write only, demonstrates refreshing stale state.
            writer.execute(text("UPDATE inventory_lots SET on_hand_quantity=49 WHERE id=:id"), {"id": a["lot"]})
        assert cached.on_hand_quantity == Decimal("50.125")
        assert repo.get_lot_for_update(a["store"], a["lot"]).on_hand_quantity == Decimal("49")
        competitor.execute(text("SET LOCAL lock_timeout='100ms'"))
        with pytest.raises(OperationalError):
            InventoryRepository(competitor).get_lot_for_update(a["store"], a["lot"])
        competitor.rollback()
        owner.rollback()
        assert InventoryRepository(competitor).get_lot_for_update(a["store"], a["lot"]).id == a["lot"]


def test_additional_scoped_row_and_logical_key_lookups(engine, graph):
    a, b = graph[100], graph[200]
    checks = [
        (IdentityRepository, "get_membership_by_id", "membership"),
        (RecipeRepository, "get_line", "line"),
        (SalesRepository, "get_daily_by_id", "sale"),
        (InventoryRepository, "get_movement", "movement"),
        (ForecastRepository, "get_prediction", "prediction"),
    ]
    with Session(engine) as fresh:
        for repository, method, key in checks:
            get = getattr(repository(fresh), method)
            loaded = get(a["store"], a[key])
            assert loaded.id == a[key]
            assert get(b["store"], a[key]) is None
            assert get(a["store"], uuid4()) is None
        supplier = SupplierRepository(fresh)
        assert supplier.get_effective_term(a["store"], a["supplier"], a["ingredient"], DAY).id == a["term"]
        assert supplier.get_effective_term(b["store"], a["supplier"], a["ingredient"], DAY) is None
        constraints = ConstraintsRepository(fresh)
        assert constraints.get_effective_budget(a["store"], DAY).id == a["budget"]
        assert constraints.get_effective_budget(a["store"], date(2026, 9, 30)) is None
        assert constraints.get_effective_safety_stock(a["store"], a["ingredient"], DAY) is None
        assert [r.id for r in DecisionRepository(fresh).list_for_forecast(a["store"], a["forecast"])] == [a["decision"]]
        assert DecisionRepository(fresh).list_for_forecast(b["store"], a["forecast"]) == []


@pytest.mark.parametrize("repository,method,model,key,field,target", [
    (RecipeRepository, "add_recipe_line", RecipeLine, "line", "ingredient_id", "ingredient"),
    (SupplierRepository, "add_supplier_term", SupplierTerm, "term", "supplier_id", "supplier"),
    (SalesRepository, "add_sales_record", SalesDaily, "sale", "product_id", "product"),
    (InventoryRepository, "add_lot", InventoryLot, "lot", "ingredient_id", "ingredient"),
    (InventoryRepository, "append_movement", InventoryMovement, "movement", "lot_id", "lot"),
    (DecisionRepository, "add_decision_run", DecisionRun, "decision", "forecast_run_id", "forecast"),
])
def test_other_related_cross_store_writes_fail_at_flush(engine, graph, repository, method, model, key, field, target):
    a, b = graph[100], graph[200]
    with Session(engine) as writer:
        source = writer.get(model, a[key])
        values = {column.name: getattr(source, column.name) for column in model.__table__.columns
                  if column.name not in {"id", "created_at", "updated_at"}}
        values[field] = b[target]
        getattr(repository(writer), method)(a["store"], model(**values))
        with pytest.raises(IntegrityError):
            writer.flush()
        writer.rollback()


def test_generated_forecast_aggregate_flush_still_rolls_back(engine, graph):
    a = graph[100]
    with Session(engine) as writer:
        run = forecast(a["store"], uuid4())
        run.id = None
        prediction = ForecastPrediction(store_id=a["store"], product_id=a["product"],
            forecast_date=DAY, p25=Decimal("1"), p50=Decimal("1"), p75=Decimal("1"))
        ForecastRepository(writer).add_forecast_run(a["store"], run, [prediction])
        run_id = run.id
        assert isinstance(run_id, UUID)
        writer.flush()
        with Session(engine) as observer:
            assert ForecastRepository(observer).get_forecast_run(a["store"], run_id) is None
        writer.rollback()
    with Session(engine) as fresh:
        assert ForecastRepository(fresh).get_forecast_run(a["store"], run_id) is None
        assert ForecastRepository(fresh).list_predictions(a["store"], run_id) == []


def running_forecast(store_id, run_id):
    row = forecast(store_id, run_id)
    row.status, row.completed_at = "RUNNING", None
    return row


def running_decision(store_id, forecast_id, run_id):
    row = decision(store_id, forecast_id, run_id)
    row.status, row.completed_at = "RUNNING", None
    row.decision_package_json, row.recommended_strategy = None, None
    return row


def complete_decision(repo, store_id, run_id):
    return repo.complete_run(store_id, run_id, completed_at=NOW,
        input_fingerprint="lifecycle-input", package_schema_version=1,
        input_snapshot_json={"stock": "50.125"},
        decision_package_json={"fixture_only": True}, recommended_strategy="BALANCED")


@pytest.mark.parametrize("terminal", ["COMPLETED", "FAILED"])
def test_repository_run_lifecycle_fresh_reload(engine, graph, terminal):
    a = graph[100]
    forecast_id, decision_id = uuid4(), uuid4()
    with Session(engine) as writer:
        forecasts, decisions = ForecastRepository(writer), DecisionRepository(writer)
        forecasts.add_forecast_run(a["store"], running_forecast(a["store"], forecast_id))
        predictions = [ForecastPrediction(store_id=a["store"], product_id=a["product"],
            forecast_date=DAY, p25=Decimal("1"), p50=Decimal("2.125"), p75=Decimal("3"))]
        assert forecasts.add_predictions(a["store"], forecast_id, predictions).status == "RUNNING"
        decisions.add_decision_run(a["store"], running_decision(a["store"], forecast_id, decision_id))
        if terminal == "COMPLETED":
            forecasts.mark_completed(a["store"], forecast_id, completed_at=NOW,
                input_fingerprint="lifecycle-input", metrics_json={"MAE": "1.125"})
            complete_decision(decisions, a["store"], decision_id)
        else:
            forecasts.mark_failed(a["store"], forecast_id, completed_at=NOW,
                error_code="FIXTURE_FAILURE", error_summary="Controlled fixture failure")
            decisions.fail_run(a["store"], decision_id, completed_at=NOW,
                error_code="FIXTURE_FAILURE", error_summary="Controlled fixture failure")
        writer.flush()
        with Session(engine) as observer:
            assert ForecastRepository(observer).get_forecast_run(a["store"], forecast_id) is None
            assert DecisionRepository(observer).get_decision_run(a["store"], decision_id) is None
        writer.commit()
    with Session(engine) as fresh:
        forecasts, decisions = ForecastRepository(fresh), DecisionRepository(fresh)
        f = forecasts.get_forecast_run(a["store"], forecast_id)
        d = decisions.get_decision_run(a["store"], decision_id)
        assert f.status == d.status == terminal
        assert f.completed_at == d.completed_at == NOW
        assert forecasts.list_predictions(a["store"], forecast_id)[0].p50 == Decimal("2.125")
        if terminal == "COMPLETED":
            assert f.metrics_json == {"MAE": "1.125"}
            assert d.input_fingerprint == "lifecycle-input"
            assert d.input_snapshot_json == {"stock": "50.125"}
            assert d.decision_package_json == {"fixture_only": True}
            assert d.recommended_strategy == "BALANCED" and d.package_schema_version == 1
        else:
            assert f.error_code == d.error_code == "FIXTURE_FAILURE"
            assert d.decision_package_json is None and d.recommended_strategy is None
        with pytest.raises(ValueError, match="RUNNING"):
            forecasts.mark_completed(a["store"], forecast_id, completed_at=NOW, input_fingerprint="overwrite")
        with pytest.raises(ValueError, match="RUNNING"):
            forecasts.mark_failed(a["store"], forecast_id, completed_at=NOW, error_code="E", error_summary="E")
        with pytest.raises(ValueError, match="RUNNING"):
            forecasts.add_predictions(a["store"], forecast_id, [])
        with pytest.raises(ValueError, match="RUNNING"):
            complete_decision(decisions, a["store"], decision_id)
        with pytest.raises(ValueError, match="RUNNING"):
            decisions.fail_run(a["store"], decision_id, completed_at=NOW, error_code="E", error_summary="E")
        fresh.commit()  # Rejections did not alter terminal content.
    with Session(engine) as fresh:
        assert ForecastRepository(fresh).get_forecast_run(a["store"], forecast_id).status == terminal
        assert DecisionRepository(fresh).get_decision_run(a["store"], decision_id).status == terminal


def test_lifecycle_wrong_store_and_missing_run_return_none(engine, graph):
    a, b = graph[100], graph[200]
    with Session(engine) as writer:
        forecasts, decisions = ForecastRepository(writer), DecisionRepository(writer)
        for forecast_id, decision_id in [(b["forecast"], b["decision"]), (uuid4(), uuid4())]:
            assert forecasts.mark_completed(a["store"], forecast_id, completed_at=NOW, input_fingerprint="x") is None
            assert forecasts.mark_failed(a["store"], forecast_id, completed_at=NOW, error_code="E", error_summary="E") is None
            assert forecasts.add_predictions(a["store"], forecast_id, []) is None
            assert complete_decision(decisions, a["store"], decision_id) is None
            assert decisions.fail_run(a["store"], decision_id, completed_at=NOW, error_code="E", error_summary="E") is None
        assert not writer.dirty and not writer.new


def test_lifecycle_multi_repository_rollback(engine, graph):
    a = graph[100]
    f_id, d_id = uuid4(), uuid4()
    with Session(engine) as writer:
        ForecastRepository(writer).add_forecast_run(a["store"], running_forecast(a["store"], f_id))
        writer.flush()
        DecisionRepository(writer).add_decision_run(a["store"], running_decision(a["store"], f_id, d_id))
        ForecastRepository(writer).mark_completed(a["store"], f_id, completed_at=NOW, input_fingerprint="x")
        complete_decision(DecisionRepository(writer), a["store"], d_id)
        writer.flush()
        writer.rollback()
    with Session(engine) as fresh:
        assert ForecastRepository(fresh).get_forecast_run(a["store"], f_id) is None
        assert DecisionRepository(fresh).get_decision_run(a["store"], d_id) is None


@pytest.mark.parametrize("kind", ["forecast", "decision"])
def test_lifecycle_lock_and_stale_session_guard(engine, graph, kind):
    a = graph[100]
    run_id = uuid4()
    cls = ForecastRepository if kind == "forecast" else DecisionRepository
    with Session(engine) as writer, writer.begin():
        if kind == "forecast":
            cls(writer).add_forecast_run(a["store"], running_forecast(a["store"], run_id))
        else:
            cls(writer).add_decision_run(a["store"], running_decision(a["store"], a["forecast"], run_id))
    def fail(repo):
        method = repo.mark_failed if kind == "forecast" else repo.fail_run
        return method(a["store"], run_id, completed_at=NOW, error_code="E", error_summary="Fixture")
    with Session(engine) as cached, Session(engine) as owner:
        get = cls(cached).get_forecast_run if kind == "forecast" else cls(cached).get_decision_run
        stale = get(a["store"], run_id)
        assert stale.status == "RUNNING"
        fail(cls(owner))
        cached.execute(text("SET LOCAL lock_timeout='100ms'"))
        with pytest.raises(OperationalError):
            fail(cls(cached))
        cached.rollback()
        # Keep a RUNNING row cached across another writer's committed transition.
        stale = get(a["store"], run_id)
        owner.commit()
        assert stale.status == "RUNNING"
        with pytest.raises(ValueError, match="RUNNING"):
            fail(cls(cached))
        assert stale.status == "FAILED"


@pytest.mark.parametrize("kind", ["forecast", "decision"])
def test_completion_rejects_second_write_before_caller_flush(engine, graph, kind):
    a = graph[100]
    run_id = uuid4()
    with Session(engine) as writer:
        if kind == "forecast":
            repo = ForecastRepository(writer)
            repo.add_forecast_run(a["store"], running_forecast(a["store"], run_id))
            metrics = {"nested": {"fixture": "original"}}
            repo.mark_completed(a["store"], run_id, completed_at=NOW,
                input_fingerprint="original", metrics_json=metrics)
            metrics["nested"]["fixture"] = "changed"
            with pytest.raises(ValueError, match="RUNNING"):
                repo.mark_completed(a["store"], run_id, completed_at=NOW, input_fingerprint="overwrite")
            prediction = ForecastPrediction(store_id=a["store"], product_id=a["product"],
                forecast_date=DAY, p25=Decimal("1"), p50=Decimal("1"), p75=Decimal("1"))
            with pytest.raises(ValueError, match="RUNNING"):
                repo.add_predictions(a["store"], run_id, [prediction])
            assert prediction not in writer
        else:
            repo = DecisionRepository(writer)
            repo.add_decision_run(a["store"], running_decision(a["store"], a["forecast"], run_id))
            snapshot, package = {"nested": {"stock": "50"}}, {"nested": {"fixture": "original"}}
            repo.complete_run(a["store"], run_id, completed_at=NOW, input_fingerprint="original",
                package_schema_version=1, input_snapshot_json=snapshot,
                decision_package_json=package, recommended_strategy="LEAN")
            snapshot["nested"]["stock"], package["nested"]["fixture"] = "0", "changed"
            with pytest.raises(ValueError, match="RUNNING"):
                complete_decision(repo, a["store"], run_id)
        writer.commit()
    with Session(engine) as fresh:
        if kind == "forecast":
            row = ForecastRepository(fresh).get_forecast_run(a["store"], run_id)
            assert row.metrics_json == {"nested": {"fixture": "original"}}
            assert ForecastRepository(fresh).list_predictions(a["store"], run_id) == []
        else:
            row = DecisionRepository(fresh).get_decision_run(a["store"], run_id)
            assert row.input_snapshot_json == {"nested": {"stock": "50"}}
            assert row.decision_package_json == {"nested": {"fixture": "original"}}
            assert row.recommended_strategy == "LEAN"
        assert row.input_fingerprint == "original"


def test_prediction_append_preconditions_stage_nothing(engine, graph):
    a, b = graph[100], graph[200]
    run_id = uuid4()
    with Session(engine) as writer:
        repo = ForecastRepository(writer)
        repo.add_forecast_run(a["store"], running_forecast(a["store"], run_id))
        writer.commit()
        valid = ForecastPrediction(store_id=a["store"], product_id=a["product"], forecast_date=DAY,
            p25=Decimal("1"), p50=Decimal("1"), p75=Decimal("1"))
        wrong = ForecastPrediction(store_id=b["store"], product_id=b["product"])
        with pytest.raises(ValueError, match="Store"):
            repo.add_predictions(a["store"], run_id, [valid, wrong])
        assert not writer.new
        wrong.store_id, wrong.forecast_run_id = a["store"], b["forecast"]
        with pytest.raises(ValueError, match="ForecastRun"):
            repo.add_predictions(a["store"], run_id, [valid, wrong])
        assert not writer.new
        assert repo.add_predictions(b["store"], run_id, [ForecastPrediction(store_id=b["store"])]) is None
        assert not writer.new
        repo.add_predictions(a["store"], run_id, [valid])
        with pytest.raises(ValueError, match="transient"):
            repo.add_predictions(a["store"], run_id, [valid])
        writer.rollback()
    with Session(engine) as fresh:
        assert ForecastRepository(fresh).list_predictions(a["store"], run_id) == []


def test_active_ingredient_constraint_versions_fresh_lookup(engine, graph):
    a, b = graph[100], graph[200]
    with Session(engine) as writer, writer.begin():
        repo = ConstraintsRepository(writer)
        for version, start, end, active in [(1, DAY, END, True),
                (2, date(2026, 10, 8), None, True), (3, DAY, None, False)]:
            repo.add_constraint(a["store"], BusinessConstraint(store_id=a["store"],
                scope_type="INGREDIENT", scope_id=a["ingredient"], constraint_type="MIN_SAFETY_STOCK",
                numeric_value=Decimal("100.125"), unit="ml", version=version,
                effective_from=start, effective_to=end, active=active))
    with Session(engine) as fresh:
        repo = ConstraintsRepository(fresh)
        for day, version in [(DAY, 1), (END, 1), (date(2026, 10, 8), 2), (date(2099, 1, 1), 2)]:
            row = repo.get_effective_safety_stock(a["store"], a["ingredient"], day)
            assert row.version == version and row.numeric_value == Decimal("100.125")
        assert repo.get_effective_safety_stock(a["store"], a["ingredient"], date(2026, 9, 30)) is None
        assert repo.get_effective_safety_stock(b["store"], a["ingredient"], DAY) is None
