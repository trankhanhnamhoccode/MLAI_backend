"""S1.7 real PostgreSQL operational paths; only shelfcash_test is owned."""
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from threading import Event
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from app.application.contracts.store import CreateStoreInput, GetStoreInput
from app.application.contracts.catalog import CreateIngredientInput, GetIngredientInput, CreateProductInput
from app.application.contracts.supplier import CreateSupplierTermInput, GetSupplierTermInput
from app.application.contracts.recipe import CreateRecipeVersionInput, GetActiveRecipeInput
from app.application.contracts.inventory import ReceiveInventoryInput, AdjustInventoryInput, GetInventoryLotInput
from app.application.contracts.sales import RecordDailySalesInput
from app.application.errors import ApplicationError, ErrorCategory
from app.application.use_cases.store import StoreUseCases
from app.application.use_cases.catalog import IngredientUseCases, ProductUseCases
from app.application.use_cases.supplier import SupplierTermUseCases
from app.application.use_cases.recipe import RecipeUseCases
from app.application.use_cases.inventory import InventoryUseCases
from app.application.use_cases.sales import SalesUseCases
from app.models import Ingredient, InventoryLot, InventoryMovement, Product, Recipe, RecipeLine, Store, Supplier, SupplierTerm
from app.repositories.identity import StoreRepository
from app.repositories.catalog import CatalogRepository
from app.repositories.supplier import SupplierRepository

STORE, PRODUCT, INGREDIENT, SUPPLIER, SECOND = [UUID(int=i) for i in range(100, 105)]
OTHER, OTHER_PRODUCT, OTHER_INGREDIENT, OTHER_SUPPLIER = [UUID(int=i) for i in range(200, 204)]
DAY, END = date(2026, 10, 1), date(2026, 10, 7)
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.fixture
def engine(database_settings: Settings) -> Iterator[Engine]:
    instance = create_database_engine(database_settings)
    try:
        yield instance
    finally:
        instance.dispose()


@pytest.fixture
def parents(engine):
    """Only lookup prerequisites; business writes under test go through use cases."""
    with Session(engine) as session, session.begin():
        for store, product, ingredient, supplier in [
            (STORE, PRODUCT, INGREDIENT, SUPPLIER), (OTHER, OTHER_PRODUCT, OTHER_INGREDIENT, OTHER_SUPPLIER)]:
            StoreRepository(session).add_store(Store(id=store, name='Fixture cafe'))
            session.flush()
            catalog = CatalogRepository(session)
            catalog.add_product(store, Product(id=product, store_id=store, name='Coffee', selling_unit='cup'))
            catalog.add_ingredient(store, Ingredient(id=ingredient, store_id=store, name='Milk', base_unit='ml', expiry_tracking=True))
            SupplierRepository(session).add_supplier(store, Supplier(id=supplier, store_id=store, name='Fixture supplier'))
        CatalogRepository(session).add_ingredient(STORE, Ingredient(id=SECOND, store_id=STORE, name='Coffee beans', base_unit='g'))


def term(**changes):
    return CreateSupplierTermInput(**(dict(store_id=STORE, supplier_id=SUPPLIER, ingredient_id=INGREDIENT,
        unit='ml', version=1, effective_from=DAY, effective_to=END, pack_size_base_quantity='15000',
        minimum_order_packs=1, pack_cost='420000', lead_time_days=3, shelf_life_days=10) | changes))


def recipe(**changes):
    return CreateRecipeVersionInput(**(dict(store_id=STORE, product_id=PRODUCT, version=1,
        effective_from=DAY, effective_to=END, yield_quantity='10', process_loss_rate='0.05',
        lines=[dict(ingredient_id=INGREDIENT, quantity='800.125', unit='ml'),
               dict(ingredient_id=SECOND, quantity='10.25', unit='g')]) | changes))


def receipt(**changes):
    return ReceiveInventoryInput(**(dict(store_id=STORE, ingredient_id=INGREDIENT, supplier_id=SUPPLIER,
        quantity='50', unit='ml', unit_cost='30.125', expiry_date=END, occurred_at=NOW,
        reference_type='SOURCE', reference_id='fixture-receipt', lot_code='LOT-1') | changes))


def receive(engine, **changes):
    with Session(engine) as writer:
        return InventoryUseCases(writer).receive(receipt(**changes)).lot.id


def adjustment(lot_id, **changes):
    return AdjustInventoryInput(**(dict(store_id=STORE, lot_id=lot_id, quantity_delta='-5',
        unit='ml', movement_type='COUNT_CORRECTION', occurred_at=NOW+timedelta(minutes=1),
        note='Confirmed physical count') | changes))


def assert_error(category, call):
    with pytest.raises(ApplicationError) as captured:
        call()
    assert captured.value.category == category


def test_store_create_close_fresh_application_read(engine):
    with Session(engine) as writer:
        result = StoreUseCases(writer).create(CreateStoreInput(name='Cafe'))
        assert not writer.in_transaction() and result.currency == 'VND'
    with Session(engine) as fresh:
        read = StoreUseCases(fresh).get(GetStoreInput(store_id=result.id))
        assert read == result and read.timezone == 'Asia/Ho_Chi_Minh'
        assert fresh.get(Store, result.id).name == 'Cafe'
        with pytest.raises(ValidationError):
            read.name = 'Changed'


def test_store_bad_input_before_write_and_missing_read(engine, monkeypatch):
    with Session(engine) as writer:
        cases = StoreUseCases(writer)
        monkeypatch.setattr(cases.stores, 'add_store', lambda *a: pytest.fail('Invalid input reached repository'))
        with pytest.raises(ValidationError):
            cases.create(CreateStoreInput.model_construct(name=' '))
        assert not writer.in_transaction()
        assert_error(ErrorCategory.NOT_FOUND, lambda: cases.get(GetStoreInput(store_id=uuid4())))
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Store)) == 0


def test_ingredient_duplicate_scope_nullable_facts_and_fresh_read(engine, parents):
    with Session(engine) as writer:
        cases = IngredientUseCases(writer)
        first = cases.create(CreateIngredientInput(store_id=STORE, name='Sugar', sku='ING001', base_unit='g'))
        assert_error(ErrorCategory.CONFLICT, lambda: cases.create(CreateIngredientInput(
            store_id=STORE, name='Duplicate', sku='ING001', base_unit='g')))
        assert not writer.in_transaction()
        second = cases.create(CreateIngredientInput(store_id=OTHER, name='Sugar', sku='ING001', base_unit='g'))
        nullable = cases.create(CreateIngredientInput(store_id=STORE, name='Unknown SKU', base_unit='g'))
        assert nullable.sku is None
    with Session(engine) as fresh:
        read = IngredientUseCases(fresh).get(GetIngredientInput(store_id=STORE, ingredient_id=first.id))
        assert read == first and not read.expiry_tracking and read.active
        assert_error(ErrorCategory.NOT_FOUND, lambda: IngredientUseCases(fresh).get(
            GetIngredientInput(store_id=STORE, ingredient_id=second.id)))
        assert fresh.scalar(select(func.count()).select_from(Ingredient).where(Ingredient.store_id == STORE, Ingredient.sku == 'ING001')) == 1


def test_ingredient_missing_store(engine):
    with Session(engine) as writer:
        assert_error(ErrorCategory.NOT_FOUND, lambda: IngredientUseCases(writer).create(
            CreateIngredientInput(store_id=uuid4(), name='Milk', base_unit='ml')))
        assert not writer.in_transaction()


def test_supplier_term_fresh_exact_pack_price_new_version_and_scoped_read(engine, parents):
    with Session(engine) as writer:
        cases = SupplierTermUseCases(writer)
        first = cases.create(term())
        second = cases.create(term(version=2, effective_from=END+timedelta(days=1), effective_to=None, pack_cost='430000.125'))
        assert first.id != second.id and not writer.in_transaction()
    with Session(engine) as fresh:
        read = SupplierTermUseCases(fresh).get(GetSupplierTermInput(store_id=STORE, supplier_term_id=first.id))
        assert read == first and read.pack_cost == Decimal('420000') and read.pack_size_base_quantity == Decimal('15000')
        assert fresh.get(SupplierTerm, second.id).pack_cost == Decimal('430000.125')
        assert_error(ErrorCategory.NOT_FOUND, lambda: SupplierTermUseCases(fresh).get(
            GetSupplierTermInput(store_id=OTHER, supplier_term_id=first.id)))


@pytest.mark.parametrize('kind', ['overlap', 'duplicate_version'])
def test_supplier_term_known_conflicts_preserve_original(engine, parents, kind):
    with Session(engine) as writer:
        cases = SupplierTermUseCases(writer)
        first = cases.create(term())
        data = term(version=2, effective_from=END, effective_to=None) if kind == 'overlap' else term(effective_from=END+timedelta(days=1), effective_to=None)
        assert_error(ErrorCategory.CONFLICT, lambda: cases.create(data))
        assert not writer.in_transaction()
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SupplierTerm)) == 1
        assert fresh.get(SupplierTerm, first.id).effective_to == END


def test_supplier_inactive_overlap_allowed(engine, parents):
    with Session(engine) as writer:
        cases = SupplierTermUseCases(writer)
        cases.create(term())
        result = cases.create(term(version=2, active=False))
        assert not result.active


@pytest.mark.parametrize('changes,category', [
    ({'supplier_id': OTHER_SUPPLIER}, ErrorCategory.NOT_FOUND),
    ({'ingredient_id': OTHER_INGREDIENT}, ErrorCategory.NOT_FOUND),
    ({'supplier_id': UUID(int=999)}, ErrorCategory.NOT_FOUND),
    ({'unit': 'L'}, ErrorCategory.VALIDATION_ERROR),
])
def test_supplier_term_current_state_validation(engine, parents, changes, category):
    with Session(engine) as writer:
        assert_error(category, lambda: SupplierTermUseCases(writer).create(term(**changes)))
        assert not writer.in_transaction()
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SupplierTerm)) == 0


def test_recipe_atomic_version_lines_fresh_read(engine, parents):
    with Session(engine) as writer:
        cases = RecipeUseCases(writer)
        first = cases.create_version(recipe())
        second = cases.create_version(recipe(version=2, effective_from=END+timedelta(days=1), effective_to=None))
        assert first.id != second.id and len(first.lines) == 2 and not writer.in_transaction()
    with Session(engine) as fresh:
        read = RecipeUseCases(fresh).get_active(GetActiveRecipeInput(store_id=STORE, product_id=PRODUCT, effective_date=DAY))
        assert read == first and read.lines[0].quantity == Decimal('800.125')
        assert fresh.get(Recipe, first.id).effective_to == END
        assert fresh.scalar(select(func.count()).select_from(RecipeLine)) == 4


@pytest.mark.parametrize('kind', ['overlap', 'duplicate_version'])
def test_recipe_known_conflicts_no_autoclose_or_overwrite(engine, parents, kind):
    with Session(engine) as writer:
        cases = RecipeUseCases(writer)
        first = cases.create_version(recipe())
        data = recipe(version=2, effective_from=END, effective_to=None) if kind == 'overlap' else recipe(effective_from=END+timedelta(days=1), effective_to=None)
        assert_error(ErrorCategory.CONFLICT, lambda: cases.create_version(data))
    with Session(engine) as fresh:
        assert fresh.get(Recipe, first.id).effective_to == END
        assert fresh.scalar(select(func.count()).select_from(Recipe)) == 1
        assert fresh.scalar(select(func.count()).select_from(RecipeLine)) == 2


@pytest.mark.parametrize('kind', ['product', 'ingredient', 'unit', 'duplicate'])
def test_recipe_invalid_line_or_scope_no_partial_header(engine, parents, kind):
    data = recipe()
    if kind == 'product':
        data = recipe(product_id=OTHER_PRODUCT)
    elif kind in ['ingredient', 'unit']:
        data = recipe(lines=[dict(ingredient_id=OTHER_INGREDIENT if kind == 'ingredient' else INGREDIENT,
            quantity='1', unit='L' if kind == 'unit' else 'ml')])
    else:
        data = data.model_copy(update={'lines': data.lines + (data.lines[0],)})
    with Session(engine) as writer:
        if kind == 'duplicate':
            with pytest.raises(ValidationError):
                RecipeUseCases(writer).create_version(data)
        else:
            assert_error(ErrorCategory.VALIDATION_ERROR if kind == 'unit' else ErrorCategory.NOT_FOUND,
                lambda: RecipeUseCases(writer).create_version(data))
        assert not writer.in_transaction()
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Recipe)) == 0


def test_recipe_downstream_constraint_failure_rolls_back_flushed_header_and_line(engine, parents, monkeypatch):
    with Session(engine) as writer:
        cases = RecipeUseCases(writer)
        original = cases.recipes.add_recipe_line
        count = 0
        def fail_second(store, line):
            nonlocal count
            count += 1
            if count == 2:
                writer.flush()
                assert writer.scalar(select(func.count()).select_from(RecipeLine)) == 1
                line.quantity = Decimal('-1')
            original(store, line)
        monkeypatch.setattr(cases.recipes, 'add_recipe_line', fail_second)
        with pytest.raises(IntegrityError):
            cases.create_version(recipe())
        assert not writer.in_transaction()
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Recipe)) == 0
        assert fresh.scalar(select(func.count()).select_from(RecipeLine)) == 0


def test_receipt_fresh_lot_and_exactly_one_movement_unknown_receipt_date(engine, parents):
    instant = datetime(2026, 10, 2, 0, 30, tzinfo=timezone(timedelta(hours=7)))
    with Session(engine) as writer:
        result = InventoryUseCases(writer).receive(receipt(occurred_at=instant))
        assert result.lot.received_date is None and not writer.in_transaction()
    with Session(engine) as fresh:
        cases = InventoryUseCases(fresh)
        query = GetInventoryLotInput(store_id=STORE, lot_id=result.lot.id)
        assert cases.get(query) == result.lot
        movements = cases.movements(query)
        assert len(movements) == 1 and movements[0].movement_type == 'RECEIPT'
        assert movements[0].quantity_delta == result.lot.on_hand_quantity == Decimal('50')
        assert movements[0].occurred_at == datetime(2026, 10, 1, 17, 30, tzinfo=timezone.utc)
        assert movements[0].reference_id == 'fixture-receipt' and movements[0].lot_id == result.lot.id
        row = fresh.get(InventoryLot, result.lot.id)
        assert row.unit_cost == Decimal('30.125') and row.received_date is None


@pytest.mark.parametrize('kind', ['ingredient', 'supplier', 'unit', 'expiry'])
def test_receipt_current_state_rejected_without_partial_state(engine, parents, kind):
    changes = {'ingredient': {'ingredient_id': OTHER_INGREDIENT}, 'supplier': {'supplier_id': OTHER_SUPPLIER},
        'unit': {'unit': 'L'}, 'expiry': {'expiry_date': None}}[kind]
    with Session(engine) as writer:
        assert_error(ErrorCategory.NOT_FOUND if kind in ['ingredient', 'supplier'] else ErrorCategory.VALIDATION_ERROR,
            lambda: InventoryUseCases(writer).receive(receipt(**changes)))
        assert not writer.in_transaction()
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(InventoryLot)) == 0
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement)) == 0


def test_untracked_receipt_can_omit_expiry_supplier_cost_and_date(engine, parents):
    lot_id = receive(engine, ingredient_id=SECOND, unit='g', supplier_id=None, unit_cost=None, expiry_date=None)
    with Session(engine) as fresh:
        row = fresh.get(InventoryLot, lot_id)
        assert row.received_date is None and row.expiry_date is None and row.unit_cost is None and row.supplier_id is None


def test_lot_code_is_not_an_invented_deduplication_key(engine, parents):
    first, second = receive(engine), receive(engine)
    assert first != second
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(InventoryLot)) == 2
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement)) == 2


@pytest.mark.parametrize('failure_stage', ['before_movement', 'after_movement_flush'])
def test_receipt_downstream_failure_rolls_back_lot_and_movement(engine, parents, monkeypatch, failure_stage):
    with Session(engine) as writer:
        cases = InventoryUseCases(writer)
        original = cases.inventory.append_movement
        def broken_movement(store, movement):
            assert writer.scalar(select(func.count()).select_from(InventoryLot)) == 1
            if failure_stage == 'after_movement_flush':
                original(store, movement)
                writer.flush()
                assert writer.scalar(select(func.count()).select_from(InventoryMovement)) == 1
            raise RuntimeError('fixture downstream receipt failure')
        monkeypatch.setattr(cases.inventory, 'append_movement', broken_movement)
        with pytest.raises(RuntimeError, match='fixture downstream receipt failure'):
            cases.receive(receipt())
        assert not writer.in_transaction()
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(InventoryLot)) == 0
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement)) == 0


@pytest.mark.parametrize('movement_type,delta,expected', [('COUNT_CORRECTION', '-5', '45'), ('MANUAL_ADJUSTMENT', '2.125', '52.125'), ('COUNT_CORRECTION', '-50', '0')])
def test_inventory_correction_fresh_balance_and_movement(engine, parents, movement_type, delta, expected):
    lot_id = receive(engine)
    with Session(engine) as writer:
        result = InventoryUseCases(writer).adjust(adjustment(lot_id, movement_type=movement_type, quantity_delta=delta))
        assert result.lot.on_hand_quantity == Decimal(expected) and not writer.in_transaction()
    with Session(engine) as fresh:
        row = fresh.get(InventoryLot, lot_id)
        assert row.on_hand_quantity == Decimal(expected)
        movements = InventoryUseCases(fresh).movements(GetInventoryLotInput(store_id=STORE, lot_id=lot_id))
        assert len(movements) == 2 and movements[1].quantity_delta == Decimal(delta)
        assert movements[1].movement_type == movement_type and movements[1].note == 'Confirmed physical count'
        assert sum((m.quantity_delta for m in movements), Decimal('0')) == row.on_hand_quantity


def test_negative_balance_rejected_no_new_movement(engine, parents):
    lot_id = receive(engine, quantity='10')
    with Session(engine) as writer:
        assert_error(ErrorCategory.VALIDATION_ERROR, lambda: InventoryUseCases(writer).adjust(adjustment(lot_id, quantity_delta='-20')))
        assert not writer.in_transaction()
    with Session(engine) as fresh:
        assert fresh.get(InventoryLot, lot_id).on_hand_quantity == Decimal('10')
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement)) == 1


def test_movement_constraint_failure_rolls_back_already_flushed_balance(engine, parents, monkeypatch):
    lot_id = receive(engine)
    with Session(engine) as writer:
        cases = InventoryUseCases(writer)
        original = cases.inventory.append_movement
        def invalid_movement(store, movement):
            writer.flush()
            assert writer.get(InventoryLot, lot_id).on_hand_quantity == Decimal('45')
            movement.quantity_delta = Decimal('0')
            original(store, movement)
        monkeypatch.setattr(cases.inventory, 'append_movement', invalid_movement)
        with pytest.raises(IntegrityError):
            cases.adjust(adjustment(lot_id))
        assert not writer.in_transaction()
    with Session(engine) as fresh:
        assert fresh.get(InventoryLot, lot_id).on_hand_quantity == Decimal('50')
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement)) == 1


@pytest.mark.parametrize('operation', ['get', 'movements', 'adjust'])
def test_inventory_wrong_store_and_missing_lot(engine, parents, operation):
    lot_id = receive(engine)
    for identifier in [lot_id, uuid4()]:
        with Session(engine) as writer:
            cases = InventoryUseCases(writer)
            data = adjustment(identifier, store_id=OTHER) if operation == 'adjust' else GetInventoryLotInput(store_id=OTHER, lot_id=identifier)
            assert_error(ErrorCategory.NOT_FOUND, lambda: getattr(cases, operation)(data))
    with Session(engine) as fresh:
        assert fresh.get(InventoryLot, lot_id).on_hand_quantity == Decimal('50')
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement)) == 1


def test_inventory_adjustment_wrong_unit_preserves_balance(engine, parents):
    lot_id = receive(engine)
    with Session(engine) as writer:
        assert_error(ErrorCategory.VALIDATION_ERROR, lambda: InventoryUseCases(writer).adjust(adjustment(lot_id, unit='L')))
    with Session(engine) as fresh:
        assert fresh.get(InventoryLot, lot_id).on_hand_quantity == Decimal('50')
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement)) == 1


def test_concurrent_inventory_corrections_lock_and_refresh_no_lost_update(engine, parents):
    lot_id = receive(engine)
    first_locked, release, second_started = Event(), Event(), Event()
    second_pid = []
    def first_writer():
        with Session(engine) as writer:
            cases = InventoryUseCases(writer)
            append = cases.inventory.append_movement
            def hold_lock(store, movement):
                writer.flush()
                first_locked.set()
                assert release.wait(10), 'Test did not release first writer'
                append(store, movement)
            cases.inventory.append_movement = hold_lock
            return cases.adjust(adjustment(lot_id)).lot.on_hand_quantity
    def second_writer():
        with Session(engine) as writer:
            cases = InventoryUseCases(writer)
            get_locked = cases.inventory.get_lot_for_update
            def observe_lock(store, lot):
                second_pid.append(writer.scalar(text('SELECT pg_backend_pid()')))
                second_started.set()
                return get_locked(store, lot)
            cases.inventory.get_lot_for_update = observe_lock
            return cases.adjust(adjustment(lot_id, quantity_delta='-7')).lot.on_hand_quantity
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(first_writer)
        try:
            assert first_locked.wait(5)
            second = pool.submit(second_writer)
            assert second_started.wait(5)
            deadline = monotonic() + 5
            while monotonic() < deadline:
                with engine.connect() as observer:
                    waiting = observer.scalar(text('SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid'), {'pid': second_pid[0]})
                if waiting == 'Lock':
                    break
                sleep(0.02)
            assert waiting == 'Lock' and not second.done()
        finally:
            release.set()
        assert first.result(timeout=5) == Decimal('45')
        assert second.result(timeout=5) == Decimal('38')
    with Session(engine) as fresh:
        assert fresh.get(InventoryLot, lot_id).on_hand_quantity == Decimal('38')
        movements = InventoryUseCases(fresh).movements(GetInventoryLotInput(store_id=STORE, lot_id=lot_id))
        assert len(movements) == 3 and sum((m.quantity_delta for m in movements), Decimal('0')) == Decimal('38')


def test_s1_operational_chain_through_application_and_fresh_database(engine):
    with Session(engine) as writer:
        store = StoreUseCases(writer).create(CreateStoreInput(name='S1 chain'))
        product = ProductUseCases(writer).create(CreateProductInput(store_id=store.id, name='Coffee', selling_unit='cup'))
        ingredient = IngredientUseCases(writer).create(CreateIngredientInput(store_id=store.id, name='Milk', base_unit='ml', expiry_tracking=True))
        # Supplier identity is an explicit repository prerequisite; no supplier API.
        supplier_id = uuid4()
        with writer.begin():
            SupplierRepository(writer).add_supplier(store.id, Supplier(id=supplier_id, store_id=store.id, name='Local supplier'))
        term_result = SupplierTermUseCases(writer).create(term(store_id=store.id, supplier_id=supplier_id, ingredient_id=ingredient.id))
        recipe_result = RecipeUseCases(writer).create_version(recipe(store_id=store.id, product_id=product.id,
            lines=[dict(ingredient_id=ingredient.id, quantity='800.125', unit='ml')]))
        sale = SalesUseCases(writer).record(RecordDailySalesInput(store_id=store.id, product_id=product.id, sales_date=DAY, quantity='10'))
        received = InventoryUseCases(writer).receive(receipt(store_id=store.id, ingredient_id=ingredient.id, supplier_id=supplier_id))
        corrected = InventoryUseCases(writer).adjust(adjustment(received.lot.id, store_id=store.id))
    with Session(engine) as fresh:
        assert StoreUseCases(fresh).get(GetStoreInput(store_id=store.id)) == store
        assert IngredientUseCases(fresh).get(GetIngredientInput(store_id=store.id, ingredient_id=ingredient.id)) == ingredient
        assert SupplierTermUseCases(fresh).get(GetSupplierTermInput(store_id=store.id, supplier_term_id=term_result.id)) == term_result
        assert RecipeUseCases(fresh).get_active(GetActiveRecipeInput(store_id=store.id, product_id=product.id, effective_date=DAY)) == recipe_result
        assert InventoryUseCases(fresh).get(GetInventoryLotInput(store_id=store.id, lot_id=received.lot.id)) == corrected.lot
        assert corrected.lot.on_hand_quantity == Decimal('45') and sale.quantity == Decimal('10')


def operational_write(session, operation, lot_id):
    if operation == 'store':
        return lambda: StoreUseCases(session).create(CreateStoreInput(name='New cafe'))
    if operation == 'ingredient':
        return lambda: IngredientUseCases(session).create(CreateIngredientInput(store_id=STORE, name='New bean', base_unit='g'))
    if operation == 'term':
        return lambda: SupplierTermUseCases(session).create(term())
    if operation == 'recipe':
        return lambda: RecipeUseCases(session).create_version(recipe())
    if operation == 'receipt':
        return lambda: InventoryUseCases(session).receive(receipt())
    return lambda: InventoryUseCases(session).adjust(adjustment(lot_id))


@pytest.mark.parametrize('operation', ['store', 'ingredient', 'term', 'recipe', 'receipt', 'adjust'])
def test_new_writers_preserve_caller_transaction(engine, parents, operation):
    lot_id = receive(engine)
    with Session(engine) as caller:
        caller.begin()
        pending = Store(name='Caller-owned work')
        caller.add(pending)
        assert_error(ErrorCategory.CONFLICT, operational_write(caller, operation, lot_id))
        assert caller.in_transaction() and pending in caller.new
        caller.commit()
        pending_id = pending.id
    with Session(engine) as fresh:
        assert fresh.get(Store, pending_id).name == 'Caller-owned work'
        assert fresh.get(InventoryLot, lot_id).on_hand_quantity == Decimal('50')
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement)) == 1


@pytest.mark.parametrize('operation', ['store', 'ingredient', 'term', 'recipe', 'receipt', 'adjust'])
def test_new_writer_commit_failure_rolls_back_flushed_state(engine, parents, monkeypatch, operation):
    lot_id = receive(engine)
    models = [Store, Ingredient, SupplierTerm, Recipe, RecipeLine, InventoryLot, InventoryMovement]
    with Session(engine) as before:
        counts = [before.scalar(select(func.count()).select_from(model)) for model in models]
    with Session(engine) as writer:
        def fail_commit():
            assert not writer.new and not writer.dirty  # use case already flushed
            raise RuntimeError('fixture commit failure')
        monkeypatch.setattr(writer, 'commit', fail_commit)
        with pytest.raises(RuntimeError, match='fixture commit failure'):
            operational_write(writer, operation, lot_id)()
        assert not writer.in_transaction()
    with Session(engine) as fresh:
        assert [fresh.scalar(select(func.count()).select_from(model)) for model in models] == counts
        assert fresh.get(InventoryLot, lot_id).on_hand_quantity == Decimal('50')


def test_adjust_refreshes_stale_cached_lot(engine, parents):
    lot_id = receive(engine)
    with Session(engine, expire_on_commit=False) as stale:
        cached = stale.get(InventoryLot, lot_id)
        stale.commit()
        with Session(engine) as other:
            InventoryUseCases(other).adjust(adjustment(lot_id))
        assert cached.on_hand_quantity == Decimal('50')
        result = InventoryUseCases(stale).adjust(adjustment(lot_id, quantity_delta='-7'))
        assert result.lot.on_hand_quantity == Decimal('38')
    with Session(engine) as fresh:
        assert fresh.get(InventoryLot, lot_id).on_hand_quantity == Decimal('38')


def test_new_reads_do_not_flush_or_commit_caller_work(engine, parents):
    lot_id = receive(engine)
    with Session(engine) as writer:
        term_id = SupplierTermUseCases(writer).create(term()).id
        RecipeUseCases(writer).create_version(recipe())
    with Session(engine) as caller:
        pending = Store(name='Pending read caller work')
        caller.add(pending)
        StoreUseCases(caller).get(GetStoreInput(store_id=STORE))
        IngredientUseCases(caller).get(GetIngredientInput(store_id=STORE, ingredient_id=INGREDIENT))
        SupplierTermUseCases(caller).get(GetSupplierTermInput(store_id=STORE, supplier_term_id=term_id))
        RecipeUseCases(caller).get_active(GetActiveRecipeInput(store_id=STORE, product_id=PRODUCT, effective_date=DAY))
        InventoryUseCases(caller).get(GetInventoryLotInput(store_id=STORE, lot_id=lot_id))
        InventoryUseCases(caller).movements(GetInventoryLotInput(store_id=STORE, lot_id=lot_id))
        assert pending in caller.new and caller.in_transaction()
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Store)) == 2
