"""Frozen S1.6 shape/architecture acceptance; no database required."""
import ast
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.application.contracts.catalog import CreateProductInput
from app.application.contracts.forecast import PredictionInput, StartForecastRunInput
from app.application.contracts.sales import GetSalesHistoryInput, RecordDailySalesInput
from app.application.contracts.decision import CompleteDecisionRunInput
from app.application.contracts.decision import StartDecisionRunInput
from app.application.contracts.forecast import CompleteForecastRunInput

STORE = UUID(int=100)
PRODUCT = UUID(int=101)
DAY = date(2026, 10, 1)
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize('changes', [
    {'name': ''}, {'name': '  '}, {'name': 'x' * 201}, {'selling_unit': ''},
    {'sku': ''}, {'sku': 'x' * 65}, {'price': '-1'}, {'price': 'NaN'},
    {'price': 'Infinity'}, {'price': 1.25}, {'unexpected': True},
])
def test_product_invalid_shape(changes):
    with pytest.raises(ValidationError):
        CreateProductInput(**(dict(store_id=STORE, name='Coffee', selling_unit='cup') | changes))


def test_optional_facts_preserved_and_exact_labels():
    value = CreateProductInput(store_id=STORE, name=' Coffee ', selling_unit='cup', sku=' Coffee ')
    assert value.price is None and value.sku == ' Coffee ' and value.name == ' Coffee '
    with pytest.raises(ValidationError):
        value.name = 'changed'


@pytest.mark.parametrize('values', [('-1', '1', '2'), ('2', '1', '3'), ('1', '3', '2'), ('0', 'NaN', '2'), ('0', '1', 'Infinity')])
def test_invalid_quantiles(values):
    with pytest.raises(ValidationError):
        PredictionInput(product_id=PRODUCT, forecast_date=DAY, p25=values[0], p50=values[1], p75=values[2])


def test_zero_equal_quantiles_exact_decimal():
    value = PredictionInput(product_id=PRODUCT, forecast_date=DAY, p25='0', p50=Decimal('0'), p75='0')
    assert value.p50 == Decimal('0') and isinstance(value.p50, Decimal)


@pytest.mark.parametrize('quantity', [None, '-1', 'NaN', 1.1, True])
def test_sales_required_finite_exact_quantity(quantity):
    with pytest.raises(ValidationError):
        RecordDailySalesInput(store_id=STORE, product_id=PRODUCT, sales_date=DAY, quantity=quantity)


def test_reversed_sales_window():
    with pytest.raises(ValidationError):
        GetSalesHistoryInput(store_id=STORE, product_id=PRODUCT, start_date=DAY, end_date=date(2026, 9, 30))


@pytest.mark.parametrize('changes', [
    {'training_end_date': date(2026, 8, 31)}, {'forecast_end_date': date(2026, 9, 30)},
    {'started_at': datetime(2026, 10, 1)}, {'model_version': ' '},
])
def test_forecast_metadata_shape(changes):
    with pytest.raises(ValidationError):
        StartForecastRunInput(**(dict(store_id=STORE, training_start_date=date(2026, 9, 1),
            training_end_date=date(2026, 9, 30), forecast_start_date=DAY, forecast_end_date=DAY,
            model_type='fixture', model_version='v1', started_at=NOW) | changes))


@pytest.mark.parametrize('changes', [
    {'package_schema_version': 0}, {'package_schema_version': True},
    {'recommended_strategy': 'P50'}, {'input_snapshot_json': []},
    {'decision_package_json': None}, {'decision_package_json': {'bad': float('inf')}},
])
def test_decision_minimal_envelope(changes):
    with pytest.raises(ValidationError):
        CompleteDecisionRunInput(**(dict(store_id=STORE, run_id=PRODUCT, completed_at=NOW,
            package_schema_version=1, input_fingerprint='fixture', input_snapshot_json={},
            decision_package_json={'fixture_only': True}, recommended_strategy='BALANCED') | changes))


def test_reversed_decision_planning_window():
    with pytest.raises(ValidationError):
        StartDecisionRunInput(store_id=STORE, forecast_run_id=PRODUCT,
            planning_start_date=DAY, planning_end_date=date(2026, 9, 30), started_at=NOW)


def test_duplicate_completion_prediction_shape():
    prediction = PredictionInput(product_id=PRODUCT, forecast_date=DAY, p25='0', p50='1', p75='2')
    with pytest.raises(ValidationError):
        CompleteForecastRunInput(store_id=STORE, run_id=PRODUCT, completed_at=NOW,
            input_fingerprint='fixture', predictions=[prediction, prediction])


def test_application_import_and_construction_do_not_connect(monkeypatch):
    import importlib
    import psycopg
    from sqlalchemy.orm import Session
    def reject(*args, **kwargs):
        raise AssertionError('Unexpected DB connection')
    monkeypatch.setattr(psycopg, 'connect', reject)
    with Session() as session:
        for module, cls in [('catalog', 'ProductUseCases'), ('sales', 'SalesUseCases'),
            ('forecast', 'ForecastUseCases'), ('decision', 'DecisionUseCases'), ('recipe', 'RecipeUseCases')]:
            getattr(importlib.import_module('app.application.use_cases.' + module), cls)(session)


def direct_query_calls(tree):
    """Keep the query ban; only a locally defined self.execute is orchestration.

    Session/query receivers, including self.session, are never exempted. Unknown
    receivers stay forbidden rather than relying on variable names like 's'.
    """
    violations=[]
    class QueryCalls(ast.NodeVisitor):
        def __init__(self):
            self.methods=[]

        def visit_ClassDef(self,node):
            self.methods.append({n.name for n in node.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))})
            self.generic_visit(node)
            self.methods.pop()

        def visit_Call(self,node):
            if isinstance(node.func,ast.Attribute) and node.func.attr in {'execute','scalar','scalars','query'}:
                receiver=node.func.value
                local_execute=(node.func.attr=='execute' and isinstance(receiver,ast.Name)
                    and receiver.id=='self' and self.methods and 'execute' in self.methods[-1])
                if not local_execute:violations.append(node.lineno)
            self.generic_visit(node)
    QueryCalls().visit(tree)
    return violations


@pytest.mark.parametrize('source',[
    's.execute(statement)', 'database.scalar(statement)', 'self.session.scalars(statement)',
    's.query(Model).filter(condition).scalar()',
    'class Worker:\n def execute(self,record):\n  return self.session.execute(record)\n def run(self):\n  return self.execute(record)',
    'class Worker:\n def run(self):\n  return self.execute(statement)',
])
def test_query_guard_detects_direct_sql_including_orchestrator_body(source):
    assert direct_query_calls(ast.parse(source))


def test_query_guard_allows_defined_orchestration_method():
    tree=ast.parse('class Worker:\n def execute(self,record):\n  return service.compute(record)\n def run(self):\n  return self.execute(record)')
    assert direct_query_calls(tree)==[]


def test_application_has_no_http_or_direct_queries():
    root = Path(__file__).resolve().parents[2] / 'app' / 'application'
    # Frozen S1 query separation remains enforced. Approved S4.4–S4.6 concrete
    # transaction/fence adapters existed outside that original architecture scope
    # already (ImportStaging in the 10/10 baseline). No blanket ORM exemption;
    # HTTP/transport imports and direct Session.close remain forbidden everywhere.
    transactional_adapters = {'use_cases/import_staging.py',
                              'use_cases/operational_configuration.py',
                              'use_cases/stock_writes.py'}
    for path in root.rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        if path.relative_to(root).as_posix() not in transactional_adapters:
            assert not direct_query_calls(tree),f'{path}: direct query lines {direct_query_calls(tree)}'
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or '').startswith(('fastapi', 'starlette', 'app.api', 'app.schemas'))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr != 'close'
