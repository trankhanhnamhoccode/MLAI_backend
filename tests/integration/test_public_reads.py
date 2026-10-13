"""Synthetic committed PostgreSQL facts through the six real HTTP routes."""
from sqlalchemy.engine import make_url

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select, text, event
from sqlalchemy.orm import Session
from tests.integration.test_auth_public import env, setup, login
from app.application.use_cases.public_reads import PublicReads
from app.models import (
    Product,
    Ingredient,
    Recipe,
    RecipeLine,
    InventoryLot,
    InventoryMovement,
    StoreMembership,
)
from app.models.auth import MembershipGrant
from app.models.read_revision import PublicReadRevision
from app.repositories.public_reads import PublicReadRepository


@pytest.fixture
def facts(env):
    receipt = setup(env)
    env[5].app.state.public_reads = PublicReads(env[2])
    store = receipt.store_id
    with Session(env[1]) as s:
        products = [
            Product(store_id=store, name=n, selling_unit="cup", price=p, active=a)
            for n, p, a in [
                ("\u0110\u00e1", Decimal("0"), True),
                ("\u0111\u00e1", None, False),
                ("Tr\u00e0", Decimal("12.34"), True),
            ]
        ]
        ingredients = [
            Ingredient(
                store_id=store,
                name=n,
                base_unit="ml",
                expiry_tracking=t,
                active=n != "Empty",
                sku="SYNTHETIC-SUGAR" if not t and n != "Empty" else None,
            )
            for n, t in [
                ("S\u1eefa", True),
                ("\u0110\u01b0\u1eddng", False),
                ("Empty", False),
            ]
        ]
        s.add_all(products + ingredients)
        s.flush()
        recipe = Recipe(
            store_id=store,
            product_id=products[0].id,
            version=1,
            effective_from=date(2026, 10, 10),
            effective_to=date(2026, 10, 10),
            yield_quantity=Decimal("10"),
            process_loss_rate=Decimal(".2"),
        )
        empty = Recipe(
            store_id=store,
            product_id=products[1].id,
            version=1,
            effective_from=date(2026, 1, 1),
            yield_quantity=Decimal("1"),
            process_loss_rate=Decimal("0"),
        )
        future = Recipe(
            store_id=store,
            product_id=products[2].id,
            version=1,
            effective_from=date(2026, 10, 11),
            yield_quantity=Decimal("1"),
            process_loss_rate=Decimal("0"),
        )
        s.add_all([recipe, empty, future])
        s.flush()
        line = RecipeLine(
            store_id=store,
            recipe_id=recipe.id,
            ingredient_id=ingredients[0].id,
            quantity=Decimal("1000.123456789012345678901"),
            unit="ml",
        )
        s.add(line)
        lots = []
        for amount, received, expiry, cost in [
            ("3", date(2026, 10, 1), date(2026, 10, 9), None),
            ("5", date(2026, 10, 1), date(2026, 10, 10), Decimal("0")),
            ("7", None, date(2026, 10, 17), None),
            ("11", date(2026, 10, 1), date(2026, 10, 18), Decimal("2.12")),
            ("0", date(2026, 10, 1), date(2026, 10, 10), None),
        ]:
            lots.append(
                InventoryLot(
                    store_id=store,
                    ingredient_id=ingredients[0].id,
                    lot_code="SAME" if amount != "0" else None,
                    on_hand_quantity=Decimal(amount),
                    unit="ml",
                    received_date=received,
                    expiry_date=expiry,
                    unit_cost=cost,
                )
            )
        lots.append(
            InventoryLot(
                store_id=store,
                ingredient_id=ingredients[1].id,
                on_hand_quantity=Decimal("4"),
                unit="ml",
                received_date=None,
                expiry_date=None,
                unit_cost=None,
            )
        )
        s.add_all(lots)
        s.flush()
        moves = [
            InventoryMovement(
                store_id=store,
                ingredient_id=ingredients[0].id,
                lot_id=lots[1].id,
                movement_type=k,
                quantity_delta=Decimal(q),
                occurred_at=datetime(2026, 10, 10, 1, tzinfo=timezone.utc),
                note="Synthetic",
            )
            for k, q in [
                ("RECEIPT", "5"),
                ("USAGE", "-1"),
                ("COUNT_CORRECTION", "-2"),
                ("MANUAL_ADJUSTMENT", "2"),
            ]
        ]
        s.add_all(moves)
        s.commit()
        ids = dict(
            store=store,
            products=[p.id for p in products],
            ingredients=[i.id for i in ingredients],
            lots=[l.id for l in lots],
            recipe=recipe.id,
            line=line.id,
            user=receipt.user_id,
        )
    assert login(env).status_code == 200
    ids["root"] = f"/api/v1/stores/{store}"
    return env, ids


def get(facts, suffix, **params):
    env, ids = facts
    return env[5].get(ids["root"] + suffix, params=params)


def test_menu_and_dated_recipe_exact_fields(facts):
    env, ids = facts
    response = get(facts, "/products", q=" DA ", limit=1)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    wire = response.json()
    assert wire["data"]["summary"] == dict(
        product_count=3, active_count=2, paused_count=1
    )
    assert wire["meta"]["pagination"]["total_count"] == 2
    allitems = []
    cursor = None
    while True:
        r = get(
            facts,
            "/products",
            q="DA",
            limit=1,
            **({"cursor": cursor} if cursor else {}),
        )
        assert r.status_code == 200, r.text
        allitems += r.json()["data"]["items"]
        cursor = r.json()["meta"]["pagination"]["next_cursor"]
        if not cursor:
            break
    assert len(allitems) == 2 and {x["selling_price"] for x in allitems} == {"0", None}
    r = get(facts, f"/products/{ids['products'][0]}")
    assert r.status_code == 200, r.text
    recipe = r.json()["data"]["recipe"]
    assert recipe["yield_quantity"] == "10" and recipe["process_loss_rate"] == "0.2"
    assert (
        recipe["ingredients"][0]["quantity"] == "1000.123456789012345678901"
        and recipe["yield_unit"] == "cup"
    )
    assert "pagination" not in r.json()["meta"]
    assert (
        get(facts, f"/products/{ids['products'][1]}").json()["meta"]["warnings"][0][
            "code"
        ]
        == "EMPTY_RECIPE"
    )
    gap = get(facts, f"/products/{ids['products'][2]}").json()
    assert (
        gap["data"]["recipe"] is None
        and gap["meta"]["warnings"][0]["code"] == "RECIPE_NOT_AVAILABLE"
    )


def test_inventory_quantities_unknown_no_writes_and_lot_cost(facts):
    env, ids = facts
    with Session(env[1]) as s:
        before = tuple(
            s.execute(
                select(
                    PublicReadRevision.menu_revision,
                    PublicReadRevision.recipe_revision,
                    PublicReadRevision.inventory_revision,
                )
            ).one()
        )
    r = get(facts, "/inventory")
    assert r.status_code == 200, r.text
    wire = r.json()
    summary = wire["data"]["summary"]
    assert (
        summary["ingredient_count"] == 3
        and summary["positive_lot_count"] == 5
        and summary["near_expiry_lot_count"] == 2
        and summary["expired_lot_count"] == 1
    )
    assert (
        summary["low_stock_ingredient_count"] is None
        and summary["unknown_assessment_ingredient_count"] == 3
    )
    rows = {x["ingredient_id"]: x for x in wire["data"]["items"]}
    milk = rows[str(ids["ingredients"][0])]
    assert (
        milk["on_hand_quantity"],
        milk["usable_quantity"],
        milk["expired_quantity"],
    ) == ("26", "23", "3")
    assert (
        milk["nearest_expiry"] == "2026-10-10"
        and milk["status"] == "near_expiry"
        and milk["stock_completeness"] == "UNKNOWN"
    )
    empty = rows[str(ids["ingredients"][2])]
    assert (
        empty["on_hand_quantity"] == "0"
        and empty["status"] == "watch"
        and empty["stock_completeness"] == "UNKNOWN"
    )
    sugar = rows[str(ids["ingredients"][1])]
    assert sugar["usable_quantity"] == "4" and {
        x["code"] for x in sugar["status_reasons"]
    } >= {"MISSING_RECEIVED_DATE", "EXPIRY_UNKNOWN"}
    detail = get(
        facts,
        f"/inventory/{ids['ingredients'][0]}",
        lot_limit=2,
        snapshot_id=wire["meta"]["snapshot_id"],
    )
    assert detail.status_code == 200, detail.text
    d = detail.json()
    assert d["data"]["lots_page"]["total_count"] == 5 and len(d["data"]["lots"]) == 2
    lots = list(d["data"]["lots"])
    cursor = d["data"]["lots_page"]["next_cursor"]
    while cursor:
        page = get(
            facts,
            f"/inventory/{ids['ingredients'][0]}/lots",
            limit=2,
            cursor=cursor,
            snapshot_id=d["meta"]["snapshot_id"],
        )
        assert page.status_code == 200, page.text
        lots += page.json()["data"]["items"]
        cursor = page.json()["meta"]["pagination"]["next_cursor"]
    assert len(lots) == len({l["lot_id"] for l in lots}) == 5
    assert [l["lot_id"] for l in lots if l["use_first"]] == [str(ids["lots"][1])]
    assert {l["cost"]["availability"] for l in lots} == {"known", "unknown"}
    assert (
        next(l for l in lots if l["lot_id"] == str(ids["lots"][1]))["cost"]["unit_cost"]
        == "0"
    )
    assert all(
        l["origin"] == "UNKNOWN" and l["location_availability"] == "unsupported"
        for l in lots
    )
    with Session(env[1]) as s:
        assert (
            tuple(
                s.execute(
                    select(
                        PublicReadRevision.menu_revision,
                        PublicReadRevision.recipe_revision,
                        PublicReadRevision.inventory_revision,
                    )
                ).one()
            )
            == before
        )
        assert len(s.scalars(select(InventoryMovement)).all()) == 4


def test_movements_signed_ties_and_recorded_source(facts):
    env, ids = facts
    items = []
    cursor = None
    while True:
        r = get(
            facts,
            f"/inventory/{ids['ingredients'][0]}/movements",
            limit=1,
            **({"cursor": cursor} if cursor else {}),
        )
        assert r.status_code == 200, r.text
        items += r.json()["data"]["items"]
        cursor = r.json()["meta"]["pagination"]["next_cursor"]
        if not cursor:
            break
    assert len(items) == 4 and {x["quantity_delta"] for x in items} == {
        "5",
        "-1",
        "-2",
        "2",
    }
    assert [x["movement_id"] for x in items] == sorted(x["movement_id"] for x in items)
    assert all(
        x["actor_user_id"] is None
        and x["origin"] == "UNKNOWN"
        and x["recorded_at"] != x["occurred_at"]
        for x in items
    )


def test_filters_missing_cross_store_and_invalid_requests(facts):
    env, ids = facts
    missing = uuid4()
    sku_result = get(facts, "/inventory", q="synthetic-sugar")
    assert sku_result.status_code == 200 and sku_result.json()["data"]["items"][0][
        "ingredient_id"
    ] == str(ids["ingredients"][1])
    r = get(
        facts,
        "/inventory",
        ingredient_id=[str(ids["ingredients"][0]), str(missing)],
        q="SUA",
        status="near_expiry,watch",
    )
    assert r.status_code == 200, r.text
    assert (
        len(r.json()["data"]["items"]) == 1
        and r.json()["data"]["missing_ingredient_ids"] == [str(missing)]
        and r.json()["data"]["summary"]["ingredient_count"] == 3
    )
    for args in [
        dict(limit=0),
        dict(limit=101),
        dict(q="  "),
        dict(q="x" * 201),
        dict(sort="cost"),
        dict(foo="bar"),
        dict(status="bad"),
    ]:
        assert get(facts, "/inventory", **args).status_code == 422
    assert get(facts, "/products", sort="unit_cost").status_code == 422
    assert (
        get(facts, "/products/" + str(ids["products"][0]).replace("-", "")).status_code
        == 422
    )
    assert get(facts, f"/products/{missing}").status_code == 404
    assert get(facts, f"/inventory/{missing}").status_code == 404
    assert env[5].get(f"/api/v1/stores/{missing}/products").status_code == 404
    assert (
        env[5].request("GET", ids["root"] + "/products", content=b"{}").status_code
        == 400
    )


def staff(env, ids, grants):
    with Session(env[1]) as s:
        member = s.scalar(
            select(StoreMembership).where(StoreMembership.store_id == ids["store"])
        )
        member.role = "STAFF"
        s.flush()
        s.add_all(
            [MembershipGrant(membership_id=member.id, permission=p) for p in grants]
        )
        s.commit()


def test_current_permission_fence_menu_redaction_cost_query_and_revoke(facts):
    env, ids = facts
    staff(env, ids, ["menu.read", "inventory.read", "ingredient.read"])
    r = get(facts, "/products")
    assert r.status_code == 200, r.text
    assert all(
        x["ingredient_count"] is None
        and x["ingredient_count_availability"] == "forbidden"
        for x in r.json()["data"]["items"]
    )
    assert r.json()["meta"]["warnings"] == []
    assert get(facts, f"/products/{ids['products'][0]}").status_code == 403
    statements = []

    def track(conn, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(env[1], "before_cursor_execute", track)
    try:
        r = get(facts, f"/inventory/{ids['ingredients'][0]}/lots")
    finally:
        event.remove(env[1], "before_cursor_execute", track)
    assert r.status_code == 200, r.text
    assert all(
        x["cost"] == dict(availability="forbidden", unit_cost=None, currency="VND")
        for x in r.json()["data"]["items"]
    )
    assert all(
        "unit_cost" not in sql.lower()
        for sql in statements
        if sql.lstrip().upper().startswith("SELECT")
    )
    with Session(env[1]) as s:
        s.scalar(select(StoreMembership)).active = False
        s.commit()
    assert get(facts, "/products").status_code == 404


def test_cursor_scope_tamper_and_revision_insert_delete_aba(facts):
    env, ids = facts
    r = get(facts, "/products", limit=1).json()
    cursor = r["meta"]["pagination"]["next_cursor"]
    assert get(facts, "/products", limit=1, cursor=cursor + "x").status_code == 422
    assert (
        get(facts, "/products", limit=1, cursor=cursor, status="active").status_code
        == 422
    )
    assert get(facts, "/inventory", limit=1, cursor=cursor).status_code == 422
    with Session(env[1]) as s:
        p = Product(store_id=ids["store"], name="insert", selling_unit="cup")
        s.add(p)
        s.flush()
        s.delete(p)
        s.commit()
    assert get(facts, "/products", limit=1, cursor=cursor).status_code == 409
    snapshot = get(facts, "/inventory").json()["meta"]["snapshot_id"]
    with Session(env[1]) as s:
        lot = s.get(InventoryLot, ids["lots"][1])
        old = lot.on_hand_quantity
        lot.on_hand_quantity = old + 1
        s.flush()
        lot.on_hand_quantity = old
        s.commit()
    assert (
        get(
            facts, f"/inventory/{ids['ingredients'][0]}/lots", snapshot_id=snapshot
        ).status_code
        == 409
    )


def test_repeatable_read_concurrent_mutation_coherent_and_closed(facts, monkeypatch):
    env, ids = facts
    original = PublicReadRepository.products
    state = []

    def mutate(repo, *args, **kwargs):
        assert (
            repo.session.scalar(text("show transaction_isolation")) == "repeatable read"
        )
        assert repo.session.scalar(text("show transaction_read_only")) == "on"
        rows = original(repo, *args, **kwargs)
        with Session(env[1]) as other:
            other.get(Product, ids["products"][0]).name = "New name"
            other.get(RecipeLine, ids["line"]).quantity = Decimal("99")
            other.commit()
        state.append(repo.session)
        return rows

    monkeypatch.setattr(PublicReadRepository, "products", mutate)
    r = get(facts, "/products")
    assert r.status_code == 200, r.text
    assert (
        next(
            x
            for x in r.json()["data"]["items"]
            if x["product_id"] == str(ids["products"][0])
        )["name"]
        == "\u0110\u00e1"
    )
    assert not state[0].in_transaction()
    monkeypatch.setattr(PublicReadRepository, "products", original)
    new = get(facts, "/products")
    assert new.json()["meta"]["data_version"] != r.json()["meta"]["data_version"]
    assert (
        get(facts, f"/products/{ids['products'][0]}").json()["data"]["recipe"][
            "ingredients"
        ][0]["quantity"]
        == "99"
    )


def test_store_date_rollover_and_recipe_switch(facts):
    env, ids = facts
    version = get(facts, "/products", limit=1).json()
    cursor = version["meta"]["pagination"]["next_cursor"]
    # Keep cookie alive: clock is moved only 20 minutes, across Store midnight.
    with Session(env[1]) as s:
        from app.models import Store

        s.get(Store, ids["store"]).timezone = "America/Los_Angeles"
        s.commit()
    env[4][0] = datetime(2026, 10, 10, 6, 50, tzinfo=timezone.utc)
    assert login(env).status_code == 200
    r = get(facts, "/products", limit=1).json()
    assert r["meta"]["as_of_date"] == "2026-10-09"
    cursor = r["meta"]["pagination"]["next_cursor"]
    env[4][0] += timedelta(minutes=20)
    assert get(facts, "/products", limit=1, cursor=cursor).status_code == 409
    assert (
        get(facts, f"/products/{ids['products'][0]}").json()["data"]["recipe"]
        is not None
    )


def test_malformed_source_and_money_representation_fail_closed(facts, test_database_url):
    env, ids = facts
    with Session(env[1]) as s:
        assert s.scalar(text("select current_database()")) == make_url(test_database_url).database
        s.execute(
            text(
                "ALTER TABLE recipe_lines DROP CONSTRAINT fk_recipe_lines_ingredient_store_unit"
            )
        )
        s.get(RecipeLine, ids["line"]).unit = "g"
        s.commit()
    r = get(facts, f"/products/{ids['products'][0]}")
    assert (
        r.status_code == 503
        and r.json()["error"]["code"] == "CATALOG_INTEGRITY_UNAVAILABLE"
    )
    with Session(env[1]) as s:
        s.get(RecipeLine, ids["line"]).unit = "ml"
        s.get(Product, ids["products"][0]).price = Decimal("1e18")
        s.commit()
    r = get(facts, "/products")
    assert (
        r.status_code == 503
        and r.json()["error"]["code"] == "CATALOG_REPRESENTATION_UNAVAILABLE"
    )


def test_missing_required_expiry_future_receipt_and_nullable_cost(facts):
    env, ids = facts
    with Session(env[1]) as s:
        lot = s.get(InventoryLot, ids["lots"][1])
        lot.expiry_date = None
        s.get(InventoryLot, ids["lots"][3]).received_date = date(2026, 10, 11)
        s.commit()
    r = get(facts, f"/inventory/{ids['ingredients'][0]}")
    assert r.status_code == 200, r.text
    stock = r.json()["data"]
    assert (
        stock["usable_quantity"] is None
        and stock["usable_availability"] == "unknown"
        and stock["usable_known_quantity"] == "7"
    )
    assert {x["code"] for x in stock["status_reasons"]} >= {
        "REQUIRED_EXPIRY_MISSING",
        "RECEIVED_DATE_IN_FUTURE",
    }
    assert stock["on_hand_quantity"] == "26" and stock["expired_quantity"] == "3"


def test_inventory_snapshot_stock_and_first_page_same_mvcc(facts, monkeypatch):
    env, ids = facts
    original = PublicReadRepository.lots
    state = []

    def change(repo, *args, **kwargs):
        assert (
            repo.session.scalar(text("show transaction_isolation")) == "repeatable read"
        )
        with Session(env[1]) as other:
            other.get(InventoryLot, ids["lots"][1]).on_hand_quantity = Decimal("500")
            other.commit()
        state.append(repo.session)
        return original(repo, *args, **kwargs)

    monkeypatch.setattr(PublicReadRepository, "lots", change)
    r = get(facts, f"/inventory/{ids['ingredients'][0]}")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["on_hand_quantity"] == "26"
    assert (
        next(x for x in data["lots"] if x["lot_id"] == str(ids["lots"][1]))["quantity"]
        == "5"
    )
    assert not state[0].in_transaction()
    monkeypatch.setattr(PublicReadRepository, "lots", original)
    assert (
        get(facts, f"/inventory/{ids['ingredients'][0]}").json()["data"][
            "on_hand_quantity"
        ]
        == "521"
    )


def test_recipe_overlap_fail_closed_not_highest_version(facts, test_database_url):
    env, ids = facts
    with Session(env[1]) as s:
        assert s.scalar(text("select current_database()")) == make_url(test_database_url).database
        s.execute(text("ALTER TABLE recipes DROP CONSTRAINT ex_recipes_product_period"))
        s.add(
            Recipe(
                store_id=ids["store"],
                product_id=ids["products"][0],
                version=2,
                effective_from=date(2026, 10, 10),
                yield_quantity=Decimal("1"),
                process_loss_rate=Decimal("0"),
            )
        )
        s.commit()
    r = get(facts, f"/products/{ids['products'][0]}")
    assert (
        r.status_code == 503
        and r.json()["error"]["code"] == "CATALOG_INTEGRITY_UNAVAILABLE"
    )


def test_cross_store_resource_and_cursor_no_disclosure(facts):
    env, ids = facts
    other = setup(env, email="other@example.test")
    with Session(env[1]) as s:
        p = Product(store_id=other.store_id, name="Other", selling_unit="cup")
        i = Ingredient(store_id=other.store_id, name="Other", base_unit="kg")
        s.add_all([p, i])
        s.commit()
        pid, iid = p.id, i.id
    assert get(facts, f"/products/{pid}").status_code == 404
    assert get(facts, f"/inventory/{iid}/lots").status_code == 404
    assert get(facts, "/inventory", ingredient_id=str(iid)).json()["data"][
        "missing_ingredient_ids"
    ] == [str(iid)]
    assert env[5].get(f"/api/v1/stores/{other.store_id}/products").status_code == 404


def test_revision_rollback_no_invalidation_and_missing_metadata_503(facts):
    env, ids = facts
    before = get(facts, "/products", limit=1).json()
    with Session(env[1]) as s:
        s.get(Product, ids["products"][0]).name = "rollback"
        s.flush()
        s.rollback()
    assert (
        get(
            facts,
            "/products",
            limit=1,
            cursor=before["meta"]["pagination"]["next_cursor"],
        ).status_code
        == 200
    )
    with Session(env[1]) as s:
        s.delete(s.get(PublicReadRevision, ids["store"]))
        s.commit()
    r = get(facts, "/products")
    assert (
        r.status_code == 503
        and r.json()["error"]["code"] == "CATALOG_INTEGRITY_UNAVAILABLE"
    )


def test_menu_only_versions_do_not_expose_recipe_changes(facts):
    env, ids = facts
    staff(env, ids, ["menu.read"])
    old = get(facts, "/products").json()
    with Session(env[1]) as s:
        s.get(RecipeLine, ids["line"]).quantity = Decimal("42")
        s.commit()
    current = get(facts, "/products").json()
    assert (
        current["meta"]["data_version"] == old["meta"]["data_version"]
        and current["meta"]["updated_at"] == old["meta"]["updated_at"]
    )
    assert current["data"] == old["data"]


def test_query_count_bounded_not_per_product(facts):
    env, ids = facts
    with Session(env[1]) as s:
        s.add_all(
            [
                Product(store_id=ids["store"], name=f"Paged {i:04}", selling_unit="cup")
                for i in range(200)
            ]
        )
        s.commit()
    counts = []
    for limit in [5, 50]:
        queries = []

        def track(conn, cursor, statement, parameters, context, many):
            if statement.lstrip().upper().startswith("SELECT"):
                queries.append(statement)

        event.listen(env[1], "before_cursor_execute", track)
        try:
            r = get(facts, "/products", limit=limit)
        finally:
            event.remove(env[1], "before_cursor_execute", track)
        assert r.status_code == 200, r.text
        assert (
            len(r.json()["data"]["items"]) == limit
            and r.json()["meta"]["pagination"]["total_count"] == 203
        )
        assert any("LIMIT" in sql and "products" in sql for sql in queries)
        counts.append(len(queries))
    assert counts[0] == counts[1]
    print("P01 total SELECTs for limit5/50 at203 Products:", counts)


def test_revision_migration_existing_store_metadata_only_and_reversible(facts, test_database_url):
    from alembic import command
    from scripts.dev import migration_config
    from sqlalchemy import inspect

    env, ids = facts
    with Session(env[1]) as s:
        assert s.scalar(text("select current_database()")) == make_url(test_database_url).database
        before = [
            s.scalar(select(Product.price).where(Product.id == ids["products"][0])),
            s.scalar(
                select(InventoryLot.on_hand_quantity).where(
                    InventoryLot.id == ids["lots"][1]
                )
            ),
        ]
    command.downgrade(migration_config(), "0011_staff_invitations")
    assert "public_read_revisions" not in inspect(env[1]).get_table_names()
    command.upgrade(migration_config(), "head")
    with Session(env[1]) as fresh:
        revision = fresh.get(PublicReadRevision, ids["store"])
        assert (
            revision.menu_revision,
            revision.recipe_revision,
            revision.inventory_revision,
        ) == (1, 1, 1)
        assert [
            fresh.scalar(select(Product.price).where(Product.id == ids["products"][0])),
            fresh.scalar(
                select(InventoryLot.on_hand_quantity).where(
                    InventoryLot.id == ids["lots"][1]
                )
            ),
        ] == before
    assert get(facts, "/products").status_code == 200


def test_authority_rechecked_after_capture_no_revoked_cost_leak(facts, monkeypatch):
    env, ids = facts
    staff(env, ids, ["inventory.read", "ingredient.read", "procurement.cost.read"])
    original = PublicReadRepository.lots

    def revoke(repo, *args, **kwargs):
        rows = original(repo, *args, **kwargs)
        with Session(env[1]) as other:
            member = other.scalar(
                select(StoreMembership).where(StoreMembership.store_id == ids["store"])
            )
            other.delete(
                other.get(MembershipGrant, (member.id, "procurement.cost.read"))
            )
            other.commit()
        return rows

    monkeypatch.setattr(PublicReadRepository, "lots", revoke)
    r = get(facts, f"/inventory/{ids['ingredients'][0]}/lots")
    assert (
        r.status_code == 409
        and r.json()["data"] is None
        and r.json()["error"]["code"] == "SNAPSHOT_NOT_AVAILABLE"
    )
    monkeypatch.setattr(PublicReadRepository, "lots", original)
    r = get(facts, f"/inventory/{ids['ingredients'][0]}/lots")
    assert r.status_code == 200
    assert all(
        x["cost"]["availability"] == "forbidden" for x in r.json()["data"]["items"]
    )


def test_unauthenticated_error_envelope_and_naive_clock_fail_closed(facts):
    env, ids = facts
    env[4][0] = env[4][0].replace(tzinfo=None)
    # Auth itself rejects invalid clock comparisons: never invent Store date/success.
    assert get(facts, "/products").status_code == 503
    env[4][0] = env[4][0].replace(tzinfo=timezone.utc)
    env[5].cookies.clear()
    r = get(facts, "/products")
    assert r.status_code == 401 and r.json()["data"] is None and r.json()["meta"] == {}


def test_client_session_token_cannot_sign_cursor_and_restart_refresh(facts):
    import hashlib, hmac

    env, ids = facts
    r = get(facts, "/products", limit=1).json()
    cursor = r["meta"]["pagination"]["next_cursor"]
    payload = cursor.split(".")[0]
    raw = env[5].cookies.get("__Host-shelfcash_session")
    forged = (
        payload
        + "."
        + hmac.new(raw.encode(), payload.encode(), hashlib.sha256).hexdigest()
    )
    response = get(facts, "/products", limit=1, cursor=forged)
    assert (
        response.status_code == 422
        and response.json()["error"]["code"] == "INVALID_CURSOR"
    )
    snapshot = get(facts, "/inventory").json()["meta"]["snapshot_id"]
    env[5].app.state.public_reads = PublicReads(env[2])
    assert get(facts, "/products", limit=1, cursor=cursor).status_code == 422
    assert (
        get(
            facts, f"/inventory/{ids['ingredients'][0]}/lots", snapshot_id=snapshot
        ).status_code
        == 409
    )
    assert get(facts, "/products", limit=1).status_code == 200
