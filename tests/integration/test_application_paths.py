"""S1.6 orchestration on shelfcash_test. Supplied runs are fixtures, not engines."""
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, select, func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from app.application.contracts.catalog import CreateProductInput, GetProductInput, ProductResult
from app.application.contracts.common import RunReferenceInput
from app.application.contracts.sales import RecordDailySalesInput, GetSalesHistoryInput
from app.application.contracts.forecast import StartForecastRunInput, CompleteForecastRunInput, FailRunInput, PredictionInput
from app.application.contracts.decision import StartDecisionRunInput, CompleteDecisionRunInput
from app.application.contracts.recipe import GetActiveRecipeInput
from app.application.errors import ApplicationError, ErrorCategory
from app.application.use_cases.catalog import ProductUseCases
from app.application.use_cases.sales import SalesUseCases
from app.application.use_cases.forecast import ForecastUseCases
from app.application.use_cases.decision import DecisionUseCases
from app.application.use_cases.recipe import RecipeUseCases
from app.models import Store, Product, Ingredient, Recipe, RecipeLine, ForecastRun, ForecastPrediction, DecisionRun, SalesDaily
from app.repositories.catalog import CatalogRepository
from app.repositories.forecast import ForecastRepository
from app.repositories.identity import StoreRepository
from app.repositories.recipe import RecipeRepository

DAY = date(2026, 10, 1)
END = date(2026, 10, 7)
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
DONE = NOW + timedelta(minutes=1)
STORE = UUID(int=100)
OTHER = UUID(int=200)
PRODUCT = UUID(int=101)
OTHER_PRODUCT = UUID(int=201)


@pytest.fixture
def engine(database_settings: Settings) -> Iterator[Engine]:
    engine = create_database_engine(database_settings)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def parents(engine):
    with Session(engine) as session, session.begin():
        for store, product in [(STORE, PRODUCT), (OTHER, OTHER_PRODUCT)]:
            StoreRepository(session).add_store(Store(id=store, name='Fixture cafe'))
            session.flush()
            CatalogRepository(session).add_product(store, Product(
                id=product, store_id=store, name='Coffee', selling_unit='cup', sku='COFFEE'))
    return STORE, PRODUCT


def forecast_input(store=STORE):
    return StartForecastRunInput(store_id=store, training_start_date=date(2026, 9, 1),
        training_end_date=date(2026, 9, 30), forecast_start_date=DAY, forecast_end_date=END,
        model_type='application_fixture', model_version='fixture-v1', started_at=NOW)


def forecast_completion(run_id, store=STORE, **changes):
    return CompleteForecastRunInput(**(dict(store_id=store, run_id=run_id, completed_at=DONE,
        input_fingerprint='fixture-input', metrics_json={'MAE': '2.125'}, predictions=[dict(
            product_id=PRODUCT if store == STORE else OTHER_PRODUCT, forecast_date=DAY,
            p25='80', p50='100.125', p75='130')]) | changes))


def start_forecast(engine, store=STORE, completed=False):
    with Session(engine) as session:
        result = ForecastUseCases(session).start(forecast_input(store))
        if completed:
            ForecastUseCases(session).complete(forecast_completion(result.id, store))
    return result.id


def start_decision(engine, forecast_id, store=STORE):
    with Session(engine) as session:
        return DecisionUseCases(session).start(StartDecisionRunInput(store_id=store,
            forecast_run_id=forecast_id, planning_start_date=DAY, planning_end_date=END, started_at=NOW)).id


def decision_completion(run_id, store=STORE):
    return CompleteDecisionRunInput(store_id=store, run_id=run_id, completed_at=DONE,
        input_fingerprint='fixture-decision', package_schema_version=1,
        input_snapshot_json={'fixture_only': True, 'inventory': {'quantity': '20.125'}},
        decision_package_json={'fixture_only': True, 'evaluations': [
            {'strategy': name, 'metric': str(index)} for index, name in enumerate(['LEAN', 'BALANCED', 'PROTECTED'])]},
        recommended_strategy='BALANCED')


def failure(run_id, store=STORE):
    return FailRunInput(store_id=store, run_id=run_id, completed_at=DONE,
        error_code='FIXTURE_FAILURE', error_summary='Sanitized fixture failure')


def assert_error(category, call):
    with pytest.raises(ApplicationError) as captured:
        call()
    assert captured.value.category == category


def test_product_commit_close_fresh_scoped_read(engine, parents):
    with Session(engine) as session:
        result = ProductUseCases(session).create(CreateProductInput(store_id=STORE,
            name='Tea', selling_unit='cup', sku='TEA', price='25000.125'))
        assert isinstance(result, ProductResult) and not session.in_transaction()
        with pytest.raises(ValidationError):
            result.price = Decimal('0')
    with Session(engine) as fresh:
        row = fresh.get(Product, result.id)
        assert row.price == Decimal('25000.125') and row.store_id == STORE
        read = ProductUseCases(fresh).get(GetProductInput(store_id=STORE, product_id=result.id))
        assert read == result
        assert_error(ErrorCategory.NOT_FOUND, lambda: ProductUseCases(fresh).get(
            GetProductInput(store_id=OTHER, product_id=result.id)))


def test_product_duplicates_are_conflicts_and_session_reusable(engine, parents):
    with Session(engine) as session:
        cases = ProductUseCases(session)
        for _ in range(2):
            assert_error(ErrorCategory.CONFLICT, lambda: cases.create(CreateProductInput(
                store_id=STORE, name='Duplicate', selling_unit='cup', sku='COFFEE')))
            assert not session.in_transaction()
        a = cases.create(CreateProductInput(store_id=STORE, name='No SKU', selling_unit='cup'))
        b = cases.create(CreateProductInput(store_id=STORE, name='No SKU', selling_unit='cup'))
        assert a.sku is None and a.price is None and a.id != b.id
        distinct = cases.create(CreateProductInput(store_id=OTHER, name='Other Tea', selling_unit='cup', sku='TEA'))
        own = cases.create(CreateProductInput(store_id=STORE, name='Tea', selling_unit='cup', sku='TEA'))
        assert distinct.store_id != own.store_id
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product).where(Product.store_id == STORE, Product.sku == 'COFFEE')) == 1


def test_product_missing_store(engine):
    with Session(engine) as session:
        assert_error(ErrorCategory.NOT_FOUND, lambda: ProductUseCases(session).create(
            CreateProductInput(store_id=uuid4(), name='Tea', selling_unit='cup')))
        assert not session.in_transaction()
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product)) == 0


def test_invalid_input_rejected_before_repository_write(engine, parents, monkeypatch):
    with Session(engine) as session:
        cases = ProductUseCases(session)
        monkeypatch.setattr(cases.catalog, 'add_product', lambda *a: pytest.fail('Repository must not be called'))
        # Even unvalidated model_construct/model_copy cannot bypass entry validation.
        invalid = CreateProductInput.model_construct(store_id=STORE, name=' ', selling_unit='cup')
        with pytest.raises(ValidationError):
            cases.create(invalid)
        assert not session.in_transaction()


def test_sales_commit_duplicate_no_correction_and_ordered_range(engine, parents):
    with Session(engine) as session:
        cases = SalesUseCases(session)
        for offset, quantity in [(2, '12.125'), (0, '0'), (1, '10.125')]:
            result = cases.record(RecordDailySalesInput(store_id=STORE, product_id=PRODUCT,
                sales_date=DAY + timedelta(days=offset), quantity=quantity))
            assert isinstance(result.quantity, Decimal) and not session.in_transaction()
        assert_error(ErrorCategory.CONFLICT, lambda: cases.record(RecordDailySalesInput(
            store_id=STORE, product_id=PRODUCT, sales_date=DAY, quantity='105')))
    with Session(engine) as fresh:
        read = SalesUseCases(fresh).history(GetSalesHistoryInput(store_id=STORE, product_id=PRODUCT,
            start_date=DAY, end_date=DAY+timedelta(days=1)))
        assert [r.sales_date for r in read] == [DAY, DAY+timedelta(days=1)]
        assert [r.quantity for r in read] == [Decimal('0'), Decimal('10.125')]
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 3


@pytest.mark.parametrize('operation', ['write', 'read'])
def test_sales_store_boundary(engine, parents, operation):
    with Session(engine) as session:
        cases = SalesUseCases(session)
        if operation == 'write':
            call = lambda: cases.record(RecordDailySalesInput(store_id=STORE, product_id=OTHER_PRODUCT, sales_date=DAY, quantity='1'))
        else:
            session.get(Product, OTHER_PRODUCT)  # Wrong Store already in identity map.
            call = lambda: cases.history(GetSalesHistoryInput(store_id=STORE, product_id=OTHER_PRODUCT, start_date=DAY, end_date=END))
        assert_error(ErrorCategory.NOT_FOUND, call)
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0


def test_forecast_complete_fresh_prediction_metadata_and_rerun(engine, parents):
    run_id = start_forecast(engine)
    with Session(engine) as session:
        result = ForecastUseCases(session).complete(forecast_completion(run_id))
        assert result.status == 'COMPLETED' and result.predictions[0].p50 == Decimal('100.125')
        assert not session.in_transaction()
        result.metrics_json.root['MAE'] = 'changed'  # Nested DTO changes cannot reach ORM.
    with Session(engine) as fresh:
        row = fresh.get(ForecastRun, run_id)
        assert row.status == 'COMPLETED' and row.completed_at == DONE
        assert row.metrics_json == {'MAE': '2.125'} and row.input_fingerprint == 'fixture-input'
        stored = fresh.scalars(select(ForecastPrediction).where(ForecastPrediction.forecast_run_id == run_id)).one()
        assert stored.p25 == Decimal('80') and stored.p50 == Decimal('100.125') and stored.p75 == Decimal('130')
    assert start_forecast(engine, completed=True) != run_id


@pytest.mark.parametrize('state', ['COMPLETED', 'FAILED'])
@pytest.mark.parametrize('operation', ['complete', 'fail'])
def test_forecast_terminal_lifecycle(engine, parents, state, operation):
    run_id = start_forecast(engine, completed=state == 'COMPLETED')
    with Session(engine) as session:
        cases = ForecastUseCases(session)
        if state == 'FAILED':
            result = cases.fail(failure(run_id))
            assert result.status == 'FAILED' and result.error_code == 'FIXTURE_FAILURE'
        call = lambda: getattr(cases, operation)(forecast_completion(run_id) if operation == 'complete' else failure(run_id))
        assert_error(ErrorCategory.INVALID_LIFECYCLE, call)
        assert not session.in_transaction()
    with Session(engine) as fresh:
        assert fresh.get(ForecastRun, run_id).status == state


@pytest.mark.parametrize('kind', ['horizon', 'product', 'time'])
def test_forecast_completion_state_validation_rolls_back(engine, parents, kind):
    run_id = start_forecast(engine)
    changes = {}
    if kind in ['horizon', 'product']:
        predictions = [PredictionInput(product_id=PRODUCT, forecast_date=DAY, p25='0', p50='1', p75='2'),
            PredictionInput(product_id=OTHER_PRODUCT if kind == 'product' else PRODUCT,
                forecast_date=END + timedelta(days=1), p25='0', p50='1', p75='2')]
        changes['predictions'] = predictions
    else:
        changes['completed_at'] = NOW - timedelta(seconds=1)
    with Session(engine) as session:
        expected = ErrorCategory.NOT_FOUND if kind == 'product' else ErrorCategory.VALIDATION_ERROR
        assert_error(expected, lambda: ForecastUseCases(session).complete(forecast_completion(run_id, **changes)))
        assert not session.in_transaction()
    with Session(engine) as fresh:
        assert fresh.get(ForecastRun, run_id).status == 'RUNNING'
        assert fresh.scalar(select(func.count()).select_from(ForecastPrediction)) == 0


def test_forecast_downstream_db_failure_rolls_back_flushed_prediction(engine, parents, monkeypatch):
    run_id = start_forecast(engine)
    with Session(engine) as session:
        cases = ForecastUseCases(session)
        original = cases.forecasts.mark_completed
        def bad_write(*args, **kwargs):
            session.flush()  # Supplied valid prediction actually reaches PostgreSQL.
            assert session.scalar(select(func.count()).select_from(ForecastPrediction)) == 1
            row = original(*args, **kwargs)
            row.model_type = ''  # Unexpected check failure must remain IntegrityError.
            return row
        monkeypatch.setattr(cases.forecasts, 'mark_completed', bad_write)
        with pytest.raises(IntegrityError):
            cases.complete(forecast_completion(run_id))
        assert not session.in_transaction()
    with Session(engine) as fresh:
        assert fresh.get(ForecastRun, run_id).status == 'RUNNING'
        assert fresh.scalar(select(func.count()).select_from(ForecastPrediction)) == 0


def test_forecast_existing_prediction_duplicate_is_conflict_atomic(engine, parents):
    run_id = start_forecast(engine)
    with Session(engine) as session, session.begin():
        ForecastRepository(session).add_predictions(STORE, run_id, [ForecastPrediction(
            store_id=STORE, product_id=PRODUCT, forecast_run_id=run_id, forecast_date=DAY,
            p25=Decimal('0'), p50=Decimal('0'), p75=Decimal('0'))])
    with Session(engine) as session:
        assert_error(ErrorCategory.CONFLICT, lambda: ForecastUseCases(session).complete(forecast_completion(run_id)))
    with Session(engine) as fresh:
        assert fresh.get(ForecastRun, run_id).status == 'RUNNING'
        assert fresh.scalar(select(func.count()).select_from(ForecastPrediction)) == 1


@pytest.mark.parametrize('operation', ['get', 'complete', 'fail'])
def test_forecast_wrong_store_or_missing_run(engine, parents, operation):
    run_id = start_forecast(engine, store=OTHER)
    for identifier in [run_id, uuid4()]:
        with Session(engine) as session:
            cases = ForecastUseCases(session)
            session.get(ForecastRun, run_id)
            data = {'get': RunReferenceInput(store_id=STORE, run_id=identifier),
                    'complete': forecast_completion(identifier), 'fail': failure(identifier)}[operation]
            if operation != 'get':
                session.rollback()  # Use cases require idle Session; cache no longer trusts state.
            assert_error(ErrorCategory.NOT_FOUND, lambda: getattr(cases, operation)(data))
    with Session(engine) as fresh:
        assert fresh.get(ForecastRun, run_id).status == 'RUNNING'


def test_decision_complete_copied_input_output_and_fresh_snapshot(engine, parents):
    forecast_id = start_forecast(engine, completed=True)
    run_id = start_decision(engine, forecast_id)
    data = decision_completion(run_id)
    with Session(engine) as session:
        result = DecisionUseCases(session).complete(data)
        assert result.status == 'COMPLETED' and result.recommended_strategy == 'BALANCED'
        assert not session.in_transaction()
        result.input_snapshot_json.root['inventory']['quantity'] = '999'
        data.decision_package_json.root['evaluations'].clear()
    with Session(engine) as fresh:
        row = fresh.get(DecisionRun, run_id)
        assert row.input_snapshot_json['inventory']['quantity'] == '20.125'
        assert len(row.decision_package_json['evaluations']) == 3
        assert row.input_fingerprint == 'fixture-decision' and row.package_schema_version == 1
        assert row.completed_at == DONE and row.status == 'COMPLETED' and row.forecast_run_id == forecast_id
        read = DecisionUseCases(fresh).get(RunReferenceInput(store_id=STORE, run_id=run_id))
        read.input_snapshot_json.root['inventory']['quantity'] = '888'
        assert row.input_snapshot_json['inventory']['quantity'] == '20.125'


@pytest.mark.parametrize('state', ['COMPLETED', 'FAILED'])
@pytest.mark.parametrize('operation', ['complete', 'fail'])
def test_decision_terminal_lifecycle(engine, parents, state, operation):
    run_id = start_decision(engine, start_forecast(engine, completed=True))
    with Session(engine) as session:
        cases = DecisionUseCases(session)
        result = cases.complete(decision_completion(run_id)) if state == 'COMPLETED' else cases.fail(failure(run_id))
        assert result.status == state
        assert_error(ErrorCategory.INVALID_LIFECYCLE, lambda: getattr(cases, operation)(
            decision_completion(run_id) if operation == 'complete' else failure(run_id)))
        assert not session.in_transaction()
    with Session(engine) as fresh:
        row = fresh.get(DecisionRun, run_id)
        assert row.status == state
        if state == 'FAILED':
            assert row.error_summary == 'Sanitized fixture failure' and row.decision_package_json is None


@pytest.mark.parametrize('kind', ['wrong_store', 'missing', 'running', 'failed'])
def test_decision_forecast_reference_validation(engine, parents, kind):
    forecast_id = uuid4() if kind == 'missing' else start_forecast(engine,
        store=OTHER if kind == 'wrong_store' else STORE, completed=kind == 'wrong_store')
    if kind == 'failed':
        with Session(engine) as session:
            ForecastUseCases(session).fail(failure(forecast_id))
    expected = ErrorCategory.NOT_FOUND if kind in ['missing', 'wrong_store'] else ErrorCategory.INVALID_LIFECYCLE
    with Session(engine) as session:
        assert_error(expected, lambda: DecisionUseCases(session).start(StartDecisionRunInput(
            store_id=STORE, forecast_run_id=forecast_id, planning_start_date=DAY, planning_end_date=END, started_at=NOW)))
        assert not session.in_transaction()
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(DecisionRun)) == 0


@pytest.mark.parametrize('operation', ['get', 'complete', 'fail'])
def test_decision_store_isolation(engine, parents, operation):
    run_id = start_decision(engine, start_forecast(engine, store=OTHER, completed=True), store=OTHER)
    with Session(engine) as session:
        cases = DecisionUseCases(session)
        data = {'get': RunReferenceInput(store_id=STORE, run_id=run_id),
                'complete': decision_completion(run_id), 'fail': failure(run_id)}[operation]
        assert_error(ErrorCategory.NOT_FOUND, lambda: getattr(cases, operation)(data))
    with Session(engine) as fresh:
        assert fresh.get(DecisionRun, run_id).status == 'RUNNING'


def test_decision_downstream_failure_after_flush_rolls_back_all_fields(engine, parents, monkeypatch):
    run_id = start_decision(engine, start_forecast(engine, completed=True))
    with Session(engine) as session:
        cases = DecisionUseCases(session)
        original = cases.decisions.complete_run
        error = OperationalError('fixture statement', {}, RuntimeError('fixture disconnect'))
        def downstream_failure(*args, **kwargs):
            row = original(*args, **kwargs)
            session.flush()
            assert row.status == 'COMPLETED'
            raise error
        monkeypatch.setattr(cases.decisions, 'complete_run', downstream_failure)
        with pytest.raises(OperationalError) as captured:
            cases.complete(decision_completion(run_id))
        assert captured.value is error and not session.in_transaction()
    with Session(engine) as fresh:
        row = fresh.get(DecisionRun, run_id)
        assert row.status == 'RUNNING' and row.completed_at is None
        assert row.input_snapshot_json is None and row.decision_package_json is None
        assert row.input_fingerprint is None and row.recommended_strategy is None and row.package_schema_version is None


def test_decision_invalid_terminal_time(engine, parents):
    run_id = start_decision(engine, start_forecast(engine, completed=True))
    data = decision_completion(run_id).model_copy(update={'completed_at': NOW-timedelta(seconds=1)})
    with Session(engine) as session:
        assert_error(ErrorCategory.VALIDATION_ERROR, lambda: DecisionUseCases(session).complete(data))
    with Session(engine) as fresh:
        assert fresh.get(DecisionRun, run_id).status == 'RUNNING'


def test_recipe_temporal_read_inclusive_open_end_typed_lines(engine, parents):
    ingredient_id, recipe_id = uuid4(), uuid4()
    with Session(engine) as session, session.begin():
        CatalogRepository(session).add_ingredient(STORE, Ingredient(id=ingredient_id, store_id=STORE, name='Milk', base_unit='ml'))
        session.flush()
        repo = RecipeRepository(session)
        repo.add_recipe(STORE, Recipe(id=recipe_id, store_id=STORE, product_id=PRODUCT,
            version=1, effective_from=DAY, effective_to=END, yield_quantity=Decimal('10')))
        repo.add_recipe(STORE, Recipe(store_id=STORE, product_id=PRODUCT,
            version=2, effective_from=END+timedelta(days=1), yield_quantity=Decimal('11')))
        session.flush()
        repo.add_recipe_line(STORE, RecipeLine(store_id=STORE, recipe_id=recipe_id,
            ingredient_id=ingredient_id, quantity=Decimal('800.125'), unit='ml'))
    with Session(engine) as fresh:
        cases = RecipeUseCases(fresh)
        for day in [DAY, END]:
            result = cases.get_active(GetActiveRecipeInput(store_id=STORE, product_id=PRODUCT, effective_date=day))
            assert result.version == 1 and result.lines[0].quantity == Decimal('800.125')
        result = cases.get_active(GetActiveRecipeInput(store_id=STORE, product_id=PRODUCT, effective_date=date(2030, 1, 1)))
        assert result.version == 2 and result.effective_to is None and result.lines == ()
        assert cases.get_active(GetActiveRecipeInput(store_id=STORE, product_id=PRODUCT, effective_date=DAY-timedelta(days=1))) is None
        assert_error(ErrorCategory.NOT_FOUND, lambda: cases.get_active(GetActiveRecipeInput(
            store_id=OTHER, product_id=PRODUCT, effective_date=DAY)))


def test_write_rejects_caller_transaction_without_rollback_or_commit(engine, parents):
    with Session(engine) as session:
        pending = Product(store_id=STORE, name='Caller pending', selling_unit='cup')
        session.add(pending)
        assert_error(ErrorCategory.CONFLICT, lambda: ProductUseCases(session).create(
            CreateProductInput(store_id=STORE, name='Use case', selling_unit='cup')))
        assert pending in session.new and session.in_transaction()
        session.rollback()
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product)) == 2


def test_reads_never_commit_or_autoflush_caller_mutations(engine, parents, monkeypatch):
    with Session(engine) as session:
        row = session.get(Product, PRODUCT)
        row.name = ''  # Would fail if ordinary autoflush occurs.
        monkeypatch.setattr(session, 'commit', lambda: pytest.fail('Read committed'))
        SalesUseCases(session).history(GetSalesHistoryInput(store_id=STORE, product_id=PRODUCT, start_date=DAY, end_date=END))
        RecipeUseCases(session).get_active(GetActiveRecipeInput(store_id=STORE, product_id=PRODUCT, effective_date=DAY))
        assert row in session.dirty
        session.rollback()
    with Session(engine) as fresh:
        assert fresh.get(Product, PRODUCT).name == 'Coffee'


def test_commit_failure_rolls_back_product(engine, parents, monkeypatch):
    with Session(engine) as session:
        def failed_commit():
            raise RuntimeError('fixture commit failure')
        monkeypatch.setattr(session, 'commit', failed_commit)
        with pytest.raises(RuntimeError, match='fixture commit failure'):
            ProductUseCases(session).create(CreateProductInput(store_id=STORE, name='Tea', selling_unit='cup'))
        assert not session.in_transaction()
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product)) == 2


def test_forecast_start_missing_store(engine):
    with Session(engine) as session:
        assert_error(ErrorCategory.NOT_FOUND, lambda: ForecastUseCases(session).start(forecast_input(uuid4())))
        assert not session.in_transaction()
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ForecastRun)) == 0


@pytest.mark.parametrize('operation', ['get', 'complete', 'fail'])
def test_decision_missing_run(engine, parents, operation):
    identifier = uuid4()
    with Session(engine) as session:
        cases = DecisionUseCases(session)
        data = {'get': RunReferenceInput(store_id=STORE, run_id=identifier),
                'complete': decision_completion(identifier), 'fail': failure(identifier)}[operation]
        assert_error(ErrorCategory.NOT_FOUND, lambda: getattr(cases, operation)(data))


@pytest.mark.parametrize('kind', ['forecast', 'decision'])
def test_lifecycle_refreshes_stale_cached_running_status(engine, parents, kind):
    forecast_id = start_forecast(engine, completed=kind == 'decision')
    identifier = forecast_id if kind == 'forecast' else start_decision(engine, forecast_id)
    cases_type = ForecastUseCases if kind == 'forecast' else DecisionUseCases
    model = ForecastRun if kind == 'forecast' else DecisionRun
    with Session(engine, expire_on_commit=False) as stale:
        row = stale.get(model, identifier)
        stale.commit()  # Idle session, deliberately cached RUNNING state.
        with Session(engine) as writer:
            cases_type(writer).complete(forecast_completion(identifier) if kind == 'forecast' else decision_completion(identifier))
        assert row.status == 'RUNNING'
        assert_error(ErrorCategory.INVALID_LIFECYCLE, lambda: cases_type(stale).fail(failure(identifier)))
        assert not stale.in_transaction()
    with Session(engine) as fresh:
        assert fresh.get(model, identifier).status == 'COMPLETED'
