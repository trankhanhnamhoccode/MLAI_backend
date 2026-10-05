"""S1.2: real PostgreSQL integrity, deterministic fixtures, fresh-session reads."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from alembic import command
import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.infrastructure.database.engine import create_database_engine
from scripts.dev import migration_config


@pytest.fixture
def engine(database_settings):
    instance = create_database_engine(database_settings)
    try:
        yield instance
    finally:
        instance.dispose()


def graph(engine):
    from app.models import Ingredient, Product, Store
    with Session(engine) as session:
        stores = [Store(name="Cafe"), Store(name="Cafe")]
        session.add_all(stores)
        session.flush()
        product = Product(store_id=stores[0].id, sku="COFFEE", name="Coffee", selling_unit="cup", price=Decimal("25000"))
        ingredient = Ingredient(store_id=stores[0].id, sku="MILK", name="Milk", base_unit="ml")
        session.add_all([product, ingredient])
        session.flush()
        ids = stores[0].id, stores[1].id, product.id, ingredient.id
        session.commit()
    return ids


def recipe(engine, **changes):
    from app.models import Recipe
    store, other, product, ingredient = graph(engine)
    values = dict(store_id=store, product_id=product, version=1, effective_from=date(2026, 1, 1), effective_to=date(2026, 3, 31), yield_quantity=Decimal("10"))
    values.update(changes)
    with Session(engine) as session:
        row = Recipe(**values)
        session.add(row)
        session.flush()
        identifier = row.id
        session.commit()
    return store, other, product, ingredient, identifier


def test_fresh_schema_and_downgrade_reupgrade(engine):
    tables = {"users", "stores", "store_memberships", "products", "ingredients", "recipes", "recipe_lines"}
    assert set(inspect(engine).get_table_names()) == tables | {"alembic_version"}
    with engine.connect() as fresh:
        assert fresh.scalar(text("SELECT current_database()")) == "shelfcash_test"
        assert fresh.scalar(text("SELECT version_num FROM alembic_version")) == "0003_catalog_recipe"
        assert fresh.scalar(text("SELECT count(*) FROM pg_constraint WHERE conname = 'ex_recipes_product_period' AND contype = 'x'")) == 1
    command.downgrade(migration_config(), "0002_identity_store")
    assert set(inspect(engine).get_table_names()) == {"alembic_version", "users", "stores", "store_memberships"}
    command.upgrade(migration_config(), "head")
    assert set(inspect(engine).get_table_names()) == tables | {"alembic_version"}


def test_graph_commit_close_reload_and_defaults(engine):
    from app.models import Ingredient, Product, Recipe, RecipeLine
    store, _, product, ingredient, recipe_id = recipe(engine)
    with Session(engine) as session:
        line = RecipeLine(store_id=store, recipe_id=recipe_id, ingredient_id=ingredient, quantity=Decimal("800.125"), unit="ml")
        session.add(line)
        session.flush()
        line_id = line.id
        session.commit()
    with Session(engine) as fresh:
        p, i, r, line = fresh.get(Product, product), fresh.get(Ingredient, ingredient), fresh.get(Recipe, recipe_id), fresh.get(RecipeLine, line_id)
        assert (p.store_id, p.sku, p.name, p.selling_unit, p.price, p.active) == (store, "COFFEE", "Coffee", "cup", Decimal("25000"), True)
        assert (i.store_id, i.sku, i.name, i.base_unit, i.expiry_tracking, i.active) == (store, "MILK", "Milk", "ml", False, True)
        assert (r.product_id, r.store_id, r.version, r.yield_quantity, r.process_loss_rate) == (product, store, 1, Decimal("10"), Decimal("0"))
        assert (r.effective_from, r.effective_to) == (date(2026, 1, 1), date(2026, 3, 31))
        assert (line.recipe_id, line.ingredient_id, line.store_id, line.quantity, line.unit) == (recipe_id, ingredient, store, Decimal("800.125"), "ml")
        for row in [p, i, r, line]:
            assert row.created_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("table,unit_column", [("products", "selling_unit"), ("ingredients", "base_unit")])
def test_sku_scope_nulls_and_nonunique_names(engine, table, unit_column):
    store, other, _, _ = graph(engine)
    sql = text(f"INSERT INTO {table} (store_id, sku, name, {unit_column}) VALUES (:store, :sku, 'Same name', 'piece')")
    with engine.begin() as connection:
        connection.execute(sql, [{"store": store, "sku": "SHARED"}, {"store": other, "sku": "SHARED"}, {"store": store, "sku": None}, {"store": store, "sku": None}])
    with engine.connect() as fresh:
        assert fresh.scalar(text(f"SELECT count(*) FROM {table} WHERE name = 'Same name'")) == 4
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(sql, {"store": store, "sku": "SHARED"})


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "-Infinity"])
def test_invalid_price(engine, value):
    store, _, _, _ = graph(engine)
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text("INSERT INTO products (store_id, name, selling_unit, price) VALUES (:store, 'Bad', 'cup', CAST(:value AS numeric))"), {"store": store, "value": value})


@pytest.mark.parametrize("value", [None, "0", "0.1234567890123456789"])
def test_valid_price_exact_decimal(engine, value):
    store, _, _, _ = graph(engine)
    with engine.begin() as connection:
        identifier = connection.scalar(text("INSERT INTO products (store_id, name, selling_unit, price) VALUES (:store, 'Valid', 'cup', CAST(:value AS numeric)) RETURNING id"), {"store": store, "value": value})
    with engine.connect() as fresh:
        assert fresh.scalar(text("SELECT price FROM products WHERE id=:id"), {"id": identifier}) == (None if value is None else Decimal(value))


@pytest.mark.parametrize("unit", ["", "   "])
def test_nonblank_base_unit(engine, unit):
    store, _, _, _ = graph(engine)
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text("INSERT INTO ingredients (store_id, name, base_unit) VALUES (:store, 'Bad', :unit)"), {"store": store, "unit": unit})


@pytest.mark.parametrize("field,value", [("yield_quantity", "0"), ("yield_quantity", "-1"), ("yield_quantity", "NaN"), ("yield_quantity", "Infinity"), ("process_loss_rate", "-0.01"), ("process_loss_rate", "1"), ("process_loss_rate", "NaN"), ("version", "0")])
def test_invalid_recipe_numbers(engine, field, value):
    _, _, _, _, identifier = recipe(engine)
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text(f"UPDATE recipes SET {field} = :value WHERE id=:id"), {"value": value, "id": identifier})


@pytest.mark.parametrize("loss", ["0", "0.05", "0.999"])
def test_valid_loss_persists(engine, loss):
    from app.models import Recipe
    *_, identifier = recipe(engine, process_loss_rate=Decimal(loss))
    with Session(engine) as fresh:
        assert fresh.get(Recipe, identifier).process_loss_rate == Decimal(loss)


def test_invalid_period(engine):
    with pytest.raises(DBAPIError):
        recipe(engine, effective_to=date(2025, 12, 31))


@pytest.mark.parametrize("start,end", [("2026-03-01", "2026-04-30"), ("2026-03-31", "2026-04-01"), ("2025-12-01", None), ("2026-01-15", "2026-02-01")])
def test_overlapping_versions_rejected_by_database(engine, start, end):
    store, _, product, _, _ = recipe(engine)
    with engine.begin() as connection, pytest.raises(IntegrityError) as failure:
        connection.execute(text("INSERT INTO recipes (store_id, product_id, version, effective_from, effective_to, yield_quantity) VALUES (:store, :product, 2, CAST(:start AS date), CAST(:end AS date), 10)"), {"store": store, "product": product, "start": start, "end": end})
    assert failure.value.orig.diag.constraint_name == "ex_recipes_product_period"


def test_adjacent_versions_resolution_and_open_end(engine):
    from app.models import Recipe
    store, _, product, _, first = recipe(engine)
    with Session(engine) as session:
        second = Recipe(store_id=store, product_id=product, version=2, effective_from=date(2026, 4, 1), yield_quantity=Decimal("10"))
        session.add(second)
        session.flush()
        second_id = second.id
        session.commit()
    with Session(engine) as fresh:
        for day, expected in [(date(2025, 12, 31), []), (date(2026, 1, 1), [first]), (date(2026, 3, 31), [first]), (date(2026, 4, 1), [second_id]), (date(2099, 1, 1), [second_id])]:
            ids = fresh.scalars(select(Recipe.id).where(Recipe.product_id == product, Recipe.effective_from <= day, (Recipe.effective_to.is_(None) | (Recipe.effective_to >= day)))).all()
            assert ids == expected
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text("UPDATE recipes SET effective_from='2026-03-31' WHERE id=:id"), {"id": second_id})


def test_version_uniqueness_without_overlap(engine):
    store, _, product, _, _ = recipe(engine)
    with engine.begin() as connection, pytest.raises(IntegrityError) as failure:
        connection.execute(text("INSERT INTO recipes (store_id, product_id, version, effective_from, yield_quantity) VALUES (:store,:product,1,'2026-04-01',10)"), {"store": store, "product": product})
    assert failure.value.orig.diag.constraint_name == "uq_recipes_product_version"


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "Infinity"])
def test_line_invalid_quantity(engine, quantity):
    store, _, _, ingredient, identifier = recipe(engine)
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text("INSERT INTO recipe_lines (store_id,recipe_id,ingredient_id,quantity,unit) VALUES (:store,:recipe,:ingredient,CAST(:qty AS numeric),'ml')"), {"store": store, "recipe": identifier, "ingredient": ingredient, "qty": quantity})


@pytest.mark.parametrize("failure", ["duplicate", "unit", "ingredient_store", "line_store", "missing_recipe", "missing_ingredient"])
def test_line_integrity(engine, failure):
    store, other, _, ingredient, identifier = recipe(engine)
    sql = text("INSERT INTO recipe_lines (store_id,recipe_id,ingredient_id,quantity,unit) VALUES (:store,:recipe,:ingredient,80,:unit)")
    values = dict(store=store, recipe=identifier, ingredient=ingredient, unit="ml")
    if failure == "duplicate":
        with engine.begin() as connection:
            connection.execute(sql, values)
    elif failure == "unit":
        values["unit"] = "L"
    elif failure == "ingredient_store":
        with engine.begin() as connection:
            values["ingredient"] = connection.scalar(text("INSERT INTO ingredients (store_id,name,base_unit) VALUES (:store,'Other milk','ml') RETURNING id"), {"store": other})
    elif failure == "line_store":
        values["store"] = other
    else:
        values["recipe" if failure == "missing_recipe" else "ingredient"] = uuid4()
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(sql, values)


@pytest.mark.parametrize("parent", ["product", "store"])
def test_recipe_cross_store_and_missing_parent(engine, parent):
    store, other, product, _ = graph(engine)
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text("INSERT INTO recipes (store_id,product_id,version,effective_from,yield_quantity) VALUES (:store,:product,1,'2026-01-01',10)"), {"store": other if parent == "store" else store, "product": product if parent == "store" else uuid4()})


@pytest.mark.parametrize("table,unit", [("products", "selling_unit"), ("ingredients", "base_unit")])
def test_catalog_missing_store(engine, table, unit):
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text(f"INSERT INTO {table} (store_id,name,{unit}) VALUES (:store,'Missing','piece')"), {"store": uuid4()})


def test_parent_unit_change_cannot_invalidate_line(engine):
    store, _, _, ingredient, identifier = recipe(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO recipe_lines (store_id,recipe_id,ingredient_id,quantity,unit) VALUES (:store,:recipe,:ingredient,80,'ml')"), {"store": store, "recipe": identifier, "ingredient": ingredient})
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text("UPDATE ingredients SET base_unit='L' WHERE id=:id"), {"id": ingredient})


def test_single_day_recipe_and_different_product_period_allowed(engine):
    from app.models import Product, Recipe
    store, _, _, _, _ = recipe(engine, effective_to=date(2026, 1, 1))
    with Session(engine) as session:
        product = Product(store_id=store, name="Other coffee", selling_unit="cup")
        session.add(product)
        session.flush()
        row = Recipe(store_id=store, product_id=product.id, version=1, effective_from=date(2026, 1, 1), yield_quantity=Decimal("1.1234567890123456789"))
        session.add(row)
        session.flush()
        identifier = row.id
        session.commit()
    with Session(engine) as fresh:
        assert fresh.get(Recipe, identifier).yield_quantity == Decimal("1.1234567890123456789")


@pytest.mark.parametrize("change", ["product_store", "recipe_store", "delete_ingredient"])
def test_parent_mutations_cannot_invalidate_graph(engine, change):
    store, other, product, ingredient, identifier = recipe(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO recipe_lines (store_id,recipe_id,ingredient_id,quantity,unit) VALUES (:store,:recipe,:ingredient,80,'ml')"), {"store": store, "recipe": identifier, "ingredient": ingredient})
    statements = {
        "product_store": ("UPDATE products SET store_id=:other WHERE id=:id", product),
        "recipe_store": ("UPDATE recipes SET store_id=:other WHERE id=:id", identifier),
        "delete_ingredient": ("DELETE FROM ingredients WHERE id=:id", ingredient),
    }
    sql, target = statements[change]
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text(sql), {"other": other, "id": target})


def test_catalog_column_types_and_integrity_constraints(engine):
    inspector = inspect(engine)
    for table in ("products", "ingredients", "recipes", "recipe_lines"):
        columns = {row["name"]: row for row in inspector.get_columns(table)}
        assert inspector.get_pk_constraint(table)["constrained_columns"] == ["id"]
        assert columns["created_at"]["type"].timezone
        for name in ("price", "yield_quantity", "process_loss_rate", "quantity"):
            if name in columns:
                assert str(columns[name]["type"]) == "NUMERIC"
        if table != "recipe_lines":
            assert columns["updated_at"]["type"].timezone
    assert {row["name"] for row in inspector.get_check_constraints("recipes")} == {"ck_recipes_version", "ck_recipes_period", "ck_recipes_yield", "ck_recipes_loss"}
    assert {tuple(row["constrained_columns"]) for row in inspector.get_foreign_keys("recipe_lines")} == {("recipe_id", "store_id"), ("ingredient_id", "store_id", "unit")}
