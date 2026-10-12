"""S3.1 contract checks only; no simulated computation or optimizer evidence."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.application.contracts.decision_execution import (
    DecisionExecutionInput, DecisionPolicy, PreparedDecisionInput, DecisionReadiness,
)
from app.application.contracts.decision_package import (
    DecisionMetric, DecisionPackageV1, DailyIngredientBalance, DailyProductFulfillment,
)
from app.application.decision_validation import validate_decision_package
from app.domain.decision.validation import PATHS, STRATEGIES, service_ratio


D = date(2026, 10, 7)
STORE, PRODUCT, INGREDIENT, RUN, RECIPE, LOT, TERM, SUPPLIER = map(UUID, (
    f'00000000-0000-0000-0000-{i:012d}' for i in range(1, 9)))


def snapshot_data():
    return dict(
        request=dict(store_id=STORE, forecast_run_id=RUN, product_ids=[PRODUCT],
                     cutoff_date=D, order_at=datetime(2026, 10, 8, tzinfo=timezone.utc)),
        timezone='UTC', currency='VND', inventory_as_of=datetime(2026, 10, 8, tzinfo=timezone.utc),
        forecast=dict(store_id=STORE, run_id=RUN, cutoff_date=D, input_fingerprint='forecast-fixture',
                      model_type='historical_quantile_baseline', model_version='1', artifact_identity=None,
                      predictions=[dict(product_id=PRODUCT, forecast_date=D+timedelta(days=i),
                                        unit='cup', p25='2', p50='3', p75='4') for i in range(1, 8)]),
        products=[dict(store_id=STORE, product_id=PRODUCT, selling_unit='cup', sku='TEA')],
        ingredients=[dict(store_id=STORE, ingredient_id=INGREDIENT, unit='g', expiry_tracking=False)],
        recipes=[dict(id=RECIPE, store_id=STORE, product_id=PRODUCT, version=1,
                      effective_from=D, yield_quantity='1', process_loss_rate='0',
                      lines=[dict(ingredient_id=INGREDIENT, quantity='1', unit='g')])],
        lots=[dict(id=LOT, store_id=STORE, ingredient_id=INGREDIENT, supplier_id=None,
                   lot_code=None, received_date=D, expiry_date=None, on_hand_quantity='30',
                   unit='g', unit_cost='2')],
        supplier_terms=[dict(id=TERM, store_id=STORE, supplier_id=SUPPLIER,
                            ingredient_id=INGREDIENT, unit='g', version=1, effective_from=D,
                            pack_size_base_quantity='10', minimum_order_packs=2,
                            pack_cost='20', lead_time_days=0, shelf_life_days=None)],
        constraints=[], policy={}, issues=[],
        assumptions=['DAY_START_CAPTURE', 'COMPLETE_INVENTORY_SCOPE', 'NO_ADDITIONAL_ORDERS'],
        source_references=[dict(entity='forecast_run', entity_id=RUN, origin='SOURCE_EXPLICIT')],
    )


def test_snapshot_detaches_nested_caller_values():
    data = snapshot_data()
    prepared = PreparedDecisionInput.model_validate(data)
    data['forecast']['predictions'][0]['p50'] = '999'
    data['recipes'][0]['lines'][0]['quantity'] = '999'
    data['assumptions'].append('mutation')
    assert prepared.forecast.predictions[0].p50 == Decimal(3)
    assert prepared.recipes[0].lines[0].quantity == Decimal(1)
    assert len(prepared.assumptions) == 3
    with pytest.raises(ValidationError):
        prepared.recipes[0].lines[0].quantity = Decimal(9)


@pytest.mark.parametrize('bad', [True, 0.5, 'NaN', 'Infinity', '-1'])
def test_policy_rejects_nonexact_nonfinite_or_negative(bad):
    with pytest.raises(ValidationError):
        DecisionPolicy(balanced_protection=bad)


def test_policy_v1_actual_values_cannot_be_relabelled():
    policy = DecisionPolicy()
    assert policy.base_service_target == Decimal('.95')
    assert policy.high_service_target == Decimal('.90')
    assert policy.balanced_protection == Decimal('.5')
    with pytest.raises(ValidationError):
        DecisionPolicy(base_service_target='.8')
    with pytest.raises(ValidationError):
        DecisionPolicy(version=True)


def test_request_overflow_duplicate_empty_scope():
    data = snapshot_data()['request']
    for change in [dict(cutoff_date=date.max), dict(product_ids=[]), dict(product_ids=[PRODUCT, PRODUCT])]:
        with pytest.raises(ValidationError):
            DecisionExecutionInput.model_validate(data | change)


@pytest.mark.parametrize('section,field,bad', [
    ('products', 'store_id', UUID(int=99)), ('ingredients', 'unit', 'kg'),
    ('lots', 'unit', 'kg'), ('supplier_terms', 'unit', 'kg'),
])
def test_snapshot_rejects_scope_and_units(section, field, bad):
    data = snapshot_data()
    data[section][0][field] = bad
    with pytest.raises(ValidationError):
        PreparedDecisionInput.model_validate(data)


def test_missing_recipe_needs_object_specific_blocker():
    data = snapshot_data()
    data['recipes'] = []
    with pytest.raises(ValidationError):
        PreparedDecisionInput.model_validate(data)
    data['issues'] = [dict(code='MISSING_RECIPE', kind='DATA_BLOCKER', field='recipe',
                           affected=[dict(entity='product', entity_id=PRODUCT)],
                           impact='BOM unavailable', suggested_action='Provide dated recipe')]
    assert PreparedDecisionInput.model_validate(data).issues[0].kind == 'DATA_BLOCKER'


def package_data():
    """Explicit hand fixture with inventory=30 and demand=2/3/4 per day.

    Construct supplied results for validation, not a fake implementation of FEFO.
    """
    known = lambda value, unit: dict(status='KNOWN', value=str(value), unit=unit)
    paths, bom, evaluations = [], [], []
    for path, qty, requested, closing, value in (
            ('LOW', 2, 14, (28, 26, 24, 22, 20, 18, 16), 32),
            ('BASE', 3, 21, (27, 24, 21, 18, 15, 12, 9), 18),
            ('HIGH', 4, 28, (26, 22, 18, 14, 10, 6, 2), 4)):
        days = [D+timedelta(days=i) for i in range(1, 8)]
        demands = [dict(product_id=PRODUCT, day=day, unit='cup', quantity=str(qty)) for day in days]
        paths.append(dict(path_id=path, demands=demands))
        bom.extend(dict(path_id=path, product_id=PRODUCT, day=day, recipe_id=RECIPE,
                        ingredient_id=INGREDIENT, unit='g', quantity=str(qty)) for day in days)
        for strategy in STRATEGIES:
            evaluations.append(dict(strategy=strategy, path_id=path, status='COMPLETE', issues=[],
                products=[dict(product_id=PRODUCT, day=day, unit='cup', requested=str(qty),
                               fulfilled=str(qty), lost_sales='0') for day in days],
                ingredients=[dict(ingredient_id=INGREDIENT, day=day, unit='g',
                                  opening=str((30, *closing)[index]), arrivals='0', consumed=str(qty),
                                  shortage='0', expired='0', waste='0', ending_usable=str(closing[index]))
                             for index, day in enumerate(days)],
                metrics=dict(requested=str(requested), fulfilled=str(requested), lost_sales='0',
                             selling_unit='cup', service=known(1, 'ratio'), purchase_outlay=known(0, 'VND'),
                             waste_value=known(0, 'VND'), ending_usable_value=known(value, 'VND'))))
    return dict(input_fingerprint='decision-fixture', policy={}, bom_version='fixture',
        candidate_version='fixture', simulator_version='fixture', recommendation_version='fixture',
        paths=paths, bom=bom, candidates=[dict(strategy=s, lines=[], purchase_outlay='0', currency='VND',
                                            equivalent_to=[other for other in STRATEGIES if other != s])
                                       for s in STRATEGIES], evaluations=evaluations, issues=[],
        recommendation=dict(status='TARGETS_MET', strategy='LEAN', explanation='Hand fixture: same zero orders',
                            evidence=[dict(strategy='LEAN', path_id='BASE', metric='service', explanation='21/21')]))


def validate(data=None, prepared=None):
    return validate_decision_package(
        PreparedDecisionInput.model_validate(prepared or snapshot_data()),
        DecisionPackageV1.model_validate(data or package_data()), expected_input_fingerprint='decision-fixture')


def test_complete_hand_supplied_package_and_zero_order_moq_exemption():
    result = validate()
    assert result.recommendation.strategy == 'LEAN'
    assert len(result.evaluations) == 9
    assert all(c.purchase_outlay == 0 for c in result.candidates)


@pytest.mark.parametrize('section', ['paths', 'candidates', 'evaluations', 'bom'])
@pytest.mark.parametrize('defect', ['missing', 'duplicate'])
def test_exact_three_by_three_and_bom_coverage(section, defect):
    data = package_data()
    if defect == 'missing':
        data[section].pop()
    else:
        data[section].append(data[section][0])
    with pytest.raises(ValueError):
        validate(data)


@pytest.mark.parametrize('bad', [True, 3.0, 'NaN', 'Infinity', '-1'])
def test_forecast_quantity_rejects_invalid_numbers(bad):
    data = snapshot_data()
    data['forecast']['predictions'][0]['p50'] = bad
    with pytest.raises(ValidationError):
        PreparedDecisionInput.model_validate(data)


@pytest.mark.parametrize('change', [dict(timezone='invalid'), dict(currency='vnd'),
    dict(inventory_as_of=datetime(2026, 10, 7, tzinfo=timezone.utc))])
def test_timezone_inventory_instant_and_currency(change):
    with pytest.raises(ValidationError):
        PreparedDecisionInput.model_validate(snapshot_data() | change)


def test_store_local_date_and_naive_order_rejected():
    data = snapshot_data()
    data['request']['order_at'] = datetime(2026, 10, 7, 23, tzinfo=timezone.utc)
    data['inventory_as_of'] = data['request']['order_at']
    data['timezone'] = 'Asia/Ho_Chi_Minh'  # local D+1
    assert PreparedDecisionInput.model_validate(data)
    data['timezone'] = 'UTC'
    with pytest.raises(ValidationError):
        PreparedDecisionInput.model_validate(data)
    data['request']['order_at'] = datetime(2026, 10, 8)
    with pytest.raises(ValidationError):
        PreparedDecisionInput.model_validate(data)


def test_forecast_missing_extra_duplicate_and_unit_mismatch():
    for defect in ('missing', 'extra', 'duplicate', 'unit'):
        data = snapshot_data()
        points = data['forecast']['predictions']
        if defect == 'missing':
            points.pop()
        elif defect == 'extra':
            points.append(points[0] | dict(product_id=UUID(int=99)))
        elif defect == 'duplicate':
            points.append(points[0])
        else:
            points[0]['unit'] = 'piece'
        with pytest.raises(ValidationError):
            PreparedDecisionInput.model_validate(data)


def test_recipe_overlap_is_not_silently_resolved():
    data = snapshot_data()
    data['recipes'].append(data['recipes'][0] | dict(id=UUID(int=100), version=2))
    with pytest.raises(ValidationError):
        PreparedDecisionInput.model_validate(data)


def issue(code, kind, entity, identity):
    return dict(code=code, kind=kind, field=code.lower(), affected=[dict(entity=entity, entity_id=identity)],
                impact='Capability unavailable', suggested_action='Provide established fact')


def test_missing_receipt_and_cost_are_warnings_tracked_expiry_blocks():
    data = snapshot_data()
    data['ingredients'][0]['expiry_tracking'] = True
    data['lots'][0].update(received_date=None, unit_cost=None)
    with pytest.raises(ValidationError):
        PreparedDecisionInput.model_validate(data)
    data['issues'] = [issue('MISSING_RECEIVED_DATE', 'WARNING', 'inventory_lot', LOT),
                      issue('MISSING_COST', 'WARNING', 'inventory_lot', LOT),
                      issue('MISSING_EXPIRY', 'DATA_BLOCKER', 'inventory_lot', LOT)]
    capture = PreparedDecisionInput.model_validate(data)
    assert capture.lots[0].received_date is None
    assert DecisionReadiness(status='DATA_BLOCKED', issues=capture.issues)
    with pytest.raises(ValidationError):
        DecisionReadiness(status='READY_FOR_COMPUTATION', issues=capture.issues)


def test_data_blocked_package_does_not_fabricate_results():
    snapshot = snapshot_data()
    snapshot['recipes'] = []
    snapshot['issues'] = [issue('MISSING_RECIPE', 'DATA_BLOCKER', 'product', PRODUCT)]
    data = package_data()
    data.update(paths=[], bom=[], candidates=[], evaluations=[], issues=snapshot['issues'],
                recommendation=dict(status='DATA_BLOCKED', strategy=None, evidence=[], explanation='Missing recipe'))
    assert validate(data, snapshot).recommendation.status == 'DATA_BLOCKED'
    data['candidates'] = package_data()['candidates']
    with pytest.raises(ValueError):
        validate(data, snapshot)


def test_metric_missing_is_null_reason_and_zero_demand_is_undefined():
    for data in [dict(status='UNKNOWN', value='0', unit='VND', reason='Unknown cost'),
                 dict(status='UNKNOWN', value=None, unit='VND'),
                 dict(status='KNOWN', value=None, unit='g')]:
        with pytest.raises(ValidationError):
            DecisionMetric(**data)
    assert service_ratio(Decimal(0), Decimal(0)) is None
    from app.application.contracts.decision_package import EvaluationMetrics
    metrics = package_data()['evaluations'][0]['metrics']
    metrics.update(requested='0', fulfilled='0', lost_sales='0')
    with pytest.raises(ValidationError):
        EvaluationMetrics(**metrics)
    metrics['service'] = dict(status='UNDEFINED', value=None, unit='ratio', reason='Zero demand')
    assert EvaluationMetrics(**metrics).service.value is None


@pytest.mark.parametrize('defect', ['incomplete', 'hard', 'changed_path', 'missing_day', 'changed_arrival',
                                     'changed_initial', 'bad_service', 'bad_identity', 'equivalence'])
def test_package_cannot_claim_complete_recommendation_with_invalid_evidence(defect):
    data = package_data()
    evaluation = data['evaluations'][0]
    if defect == 'incomplete':
        evaluation['status'] = 'INCOMPLETE'
    elif defect == 'hard':
        evaluation.update(status='HARD_INFEASIBLE', issues=[issue('LIMIT', 'HARD_VIOLATION', 'store', STORE)])
    elif defect == 'changed_path':
        data['paths'][0]['demands'][0]['quantity'] = '999'
    elif defect == 'missing_day':
        evaluation['products'].pop()
    elif defect in ('changed_arrival', 'changed_initial'):
        row = evaluation['ingredients'][0]
        row['arrivals' if defect == 'changed_arrival' else 'opening'] = '1' if defect == 'changed_arrival' else '31'
        row['ending_usable'] = '29'
    elif defect == 'bad_service':
        evaluation['metrics']['service']['value'] = '.5'
    elif defect == 'bad_identity':
        data['input_fingerprint'] = 'different'
    else:
        data['candidates'][0]['equivalent_to'] = []
    with pytest.raises(ValueError):
        validate(data)


def test_conservation_is_independent_of_decimal_context():
    from decimal import localcontext
    with localcontext() as context:
        context.prec = 2
        assert DailyIngredientBalance(ingredient_id=INGREDIENT, day=D, unit='g', opening='1000.001',
            arrivals='1000.002', consumed='1', shortage='0', expired='0', waste='0', ending_usable='1999.003')
        assert DailyProductFulfillment(product_id=PRODUCT, day=D, unit='cup', requested='1000.003',
            fulfilled='1000.001', lost_sales='.002')
        assert service_ratio(Decimal(1), Decimal(3)) == Decimal('0.'+'3'*50)


def test_public_entrypoint_revalidates_constructed_and_copied_instances():
    prepared = PreparedDecisionInput.model_validate(snapshot_data())
    forged = prepared.model_copy(update={'lots': (prepared.lots[0].model_copy(update={'unit':'kg'}),)})
    with pytest.raises(ValidationError):
        validate_decision_package(forged, DecisionPackageV1.model_validate(package_data()),
                                 expected_input_fingerprint='decision-fixture')


def test_policy_and_snapshot_values_survive_live_changes_and_ordering():
    data = snapshot_data()
    snapshot = PreparedDecisionInput.model_validate(data)
    data['supplier_terms'][0]['pack_cost'] = '999'
    data['policy']['balanced_protection'] = '.75'
    assert snapshot.supplier_terms[0].pack_cost == Decimal(20)
    assert snapshot.policy.balanced_protection == Decimal('.5')
    assert PreparedDecisionInput.model_validate_json(snapshot.model_dump_json()) == snapshot


def positive_order_data():
    data = package_data()
    # Supplied fixture: all strategies buy the same two packs at D+1.
    for candidate in data['candidates']:
        candidate.update(purchase_outlay='40', lines=[dict(supplier_term_id=TERM,
            ingredient_id=INGREDIENT, unit='g', packs=2, quantity='20', purchase_outlay='40',
            arrival_date=D+timedelta(days=1), expiry_date=None)])
    for evaluation in data['evaluations']:
        evaluation['metrics']['purchase_outlay']['value'] = '40'
        evaluation['metrics']['ending_usable_value']['value'] = str(
            int(evaluation['metrics']['ending_usable_value']['value']) + 40)
        for index, row in enumerate(evaluation['ingredients']):
            if index == 0:
                row['arrivals'] = '20'
            else:
                row['opening'] = str(int(row['opening']) + 20)
            row['ending_usable'] = str(int(row['ending_usable']) + 20)
    return data


def test_positive_pack_order_validates_and_fixed_order_is_shared_by_paths():
    assert validate(positive_order_data())


@pytest.mark.parametrize('change', [dict(packs=1), dict(packs=True), dict(packs=2.0),
    dict(quantity='21'), dict(purchase_outlay='41'), dict(unit='kg'),
    dict(arrival_date=D), dict(expiry_date=D+timedelta(days=1)),
    dict(supplier_term_id=UUID(int=999))])
def test_positive_order_pack_moq_cost_unit_arrival_and_no_fabricated_expiry(change):
    data = positive_order_data()
    data['candidates'][0]['lines'][0].update(change)
    with pytest.raises(ValueError):
        validate(data)


def test_hard_budget_exact_currency_and_known_limit():
    snapshot = snapshot_data()
    snapshot['constraints'] = [dict(id=UUID(int=90), store_id=STORE, version=1,
        kind='BUDGET_LIMIT', ingredient_id=None, value='39', unit='VND', effective_from=D)]
    with pytest.raises(ValueError):
        validate(positive_order_data(), snapshot)
    snapshot['constraints'][0]['value'] = '40'
    assert validate(positive_order_data(), snapshot)
    snapshot['constraints'][0]['unit'] = 'USD'
    with pytest.raises(ValidationError):
        PreparedDecisionInput.model_validate(snapshot)


def test_tracked_purchased_stock_requires_established_shelf_life():
    snapshot = snapshot_data()
    snapshot['ingredients'][0]['expiry_tracking'] = True
    snapshot['lots'][0]['expiry_date'] = D+timedelta(days=8)
    with pytest.raises(ValueError):
        validate(positive_order_data(), snapshot)
    snapshot['supplier_terms'][0]['shelf_life_days'] = 7
    data = positive_order_data()
    for candidate in data['candidates']:
        candidate['lines'][0]['expiry_date'] = D+timedelta(days=8)
    # Contract arrival/expiry boundary only; no FEFO algorithm is exercised.
    assert validate(data, snapshot)


def test_lot_received_after_as_of_instant_is_not_initial_stock():
    snapshot = snapshot_data()
    snapshot['lots'][0]['received_date'] = D+timedelta(days=2)
    with pytest.raises(ValueError, match='Initial balance'):
        validate(prepared=snapshot)


def test_missing_cost_cannot_be_fake_known_zero_ending_value():
    snapshot = snapshot_data()
    snapshot['lots'][0]['unit_cost'] = None
    snapshot['issues'] = [issue('MISSING_COST', 'WARNING', 'inventory_lot', LOT)]
    data = package_data()
    data['issues'] = snapshot['issues']
    with pytest.raises(ValueError, match='unknown lot cost'):
        validate(data, snapshot)
    for evaluation in data['evaluations']:
        evaluation['metrics']['ending_usable_value'] = dict(status='UNKNOWN', value=None, unit='VND',
                                                         reason='Lot cost unavailable')
    assert validate(data, snapshot)


def test_capture_issues_cannot_be_dropped_from_package():
    snapshot = snapshot_data()
    snapshot['issues'] = [issue('AGE_UNAVAILABLE', 'WARNING', 'inventory_lot', LOT)]
    with pytest.raises(ValueError, match='preserve'):
        validate(prepared=snapshot)


def test_degraded_status_cannot_be_claimed_when_targets_are_met():
    data = package_data()
    data['recommendation'].update(status='TARGETS_NOT_MET', strategy=None)
    with pytest.raises(ValueError, match='best eligible'):
        validate(data)


def test_domain_validation_has_no_boundary_or_io_dependency(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    script = '''
import sys
class Guard:
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in {'pydantic', 'sqlalchemy', 'fastapi', 'psycopg', 'httpx'} or name.startswith(('app.application', 'app.models', 'app.infrastructure', 'app.api')):
            raise AssertionError(name)
sys.meta_path.insert(0, Guard())
from app.domain.decision.validation import service_ratio
from decimal import Decimal
assert service_ratio(Decimal(1), Decimal(2)) == Decimal('.5')
'''
    result = subprocess.run([sys.executable, '-c', script], cwd=tmp_path, capture_output=True, text=True,
        env=os.environ | {'PYTHONPATH': str(Path(__file__).resolve().parents[2]), 'PYTHONDONTWRITEBYTECODE': '1'})
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_even_unselected_incomplete_evaluation_prevents_selection():
    data = package_data()
    data['evaluations'][-1]['status'] = 'INCOMPLETE'  # PROTECTED, while LEAN is selected
    with pytest.raises(ValueError, match='All nine'):
        validate(data)
    data['recommendation'].update(status='EVALUATION_INCOMPLETE', strategy=None)
    assert validate(data).recommendation.strategy is None


def test_all_hard_invalid_has_evidence_and_no_winner():
    data = package_data()
    for evaluation in data['evaluations']:
        evaluation.update(status='HARD_INFEASIBLE', issues=[issue('CAPACITY', 'HARD_VIOLATION', 'store', STORE)])
    data['recommendation'].update(status='HARD_INFEASIBLE', strategy=None)
    assert validate(data).recommendation.status == 'HARD_INFEASIBLE'
    data['evaluations'][0]['issues'] = []
    with pytest.raises(ValidationError):
        DecisionPackageV1.model_validate(data)


def test_zero_demand_package_targets_vacuous_but_service_metric_null():
    snapshot, data = snapshot_data(), package_data()
    for point in snapshot['forecast']['predictions']:
        point.update(p25='0', p50='0', p75='0')
    for path in data['paths']:
        for demand in path['demands']:
            demand['quantity'] = '0'
    for contribution in data['bom']:
        contribution['quantity'] = '0'
    for evaluation in data['evaluations']:
        for product in evaluation['products']:
            product.update(requested='0', fulfilled='0', lost_sales='0')
        for ingredient in evaluation['ingredients']:
            ingredient.update(opening='30', consumed='0', ending_usable='30')
        evaluation['metrics'].update(requested='0', fulfilled='0', lost_sales='0',
            service=dict(status='UNDEFINED', value=None, unit='ratio', reason='Zero demand'),
            ending_usable_value=dict(status='KNOWN', value='60', unit='VND'))
    assert validate(data, snapshot).recommendation.status == 'TARGETS_MET'


def test_explicit_zero_line_is_moq_exempt_and_equivalent_to_empty_basket():
    data = package_data()
    data['candidates'][0]['lines'] = [dict(supplier_term_id=TERM, ingredient_id=INGREDIENT,
        unit='g', packs=0, quantity='0', purchase_outlay='0', arrival_date=D+timedelta(days=1), expiry_date=None)]
    assert validate(data)


@pytest.mark.parametrize('change', [dict(fulfilled='3', lost_sales='0'),
                                     dict(fulfilled='-1'), dict(lost_sales='NaN')])
def test_product_fulfillment_is_bounded_and_conserved(change):
    with pytest.raises(ValidationError):
        DailyProductFulfillment(**(dict(product_id=PRODUCT, day=D, unit='cup', requested='2',
                                       fulfilled='1', lost_sales='1') | change))


def test_future_lead_and_shelf_date_overflow_rejects_before_claimed_completion():
    snapshot = snapshot_data()
    snapshot['supplier_terms'][0]['lead_time_days'] = 10**9
    with pytest.raises(ValidationError):
        PreparedDecisionInput.model_validate(snapshot)
    snapshot = snapshot_data()
    snapshot['supplier_terms'][0]['shelf_life_days'] = 10**9
    with pytest.raises(ValueError, match='Arrival date'):
        validate(positive_order_data(), snapshot)


def test_snapshot_scope_cannot_mix_selling_units_to_make_service_metric():
    snapshot = snapshot_data()
    second = UUID(int=100)
    snapshot['request']['product_ids'].append(second)
    snapshot['products'].append(dict(store_id=STORE, product_id=second, selling_unit='portion', sku='FOOD'))
    with pytest.raises(ValidationError, match='one selling unit'):
        PreparedDecisionInput.model_validate(snapshot)


def test_store_timezone_conversion_overflow_is_validation_error():
    data = snapshot_data()
    data['request']['cutoff_date'] = date(9999, 12, 24)
    data['request']['order_at'] = datetime(9999, 12, 31, 23, tzinfo=timezone.utc)
    data['inventory_as_of'] = data['request']['order_at']
    data['timezone'] = 'Pacific/Kiritimati'
    with pytest.raises(ValidationError, match='Store-local date range'):
        PreparedDecisionInput.model_validate(data)


def test_different_dst_fold_instants_are_not_same_as_of():
    from zoneinfo import ZoneInfo
    data = snapshot_data()
    zone = ZoneInfo('America/New_York')
    data['request']['cutoff_date'] = date(2026, 10, 31)
    data['request']['order_at'] = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
    data['inventory_as_of'] = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=1)
    data['timezone'] = 'America/New_York'
    with pytest.raises(ValidationError, match='as-of snapshot'):
        PreparedDecisionInput.model_validate(data)


def test_utc_normalization_overflow_rejects_at_boundary():
    from zoneinfo import ZoneInfo
    data = snapshot_data()['request']
    data['order_at'] = datetime(1, 1, 1, tzinfo=ZoneInfo('Etc/GMT-14'))
    with pytest.raises(ValidationError, match='UTC date range'):
        DecisionExecutionInput.model_validate(data)


def test_service_context_does_not_underflow_finite_tiny_ratio_to_fake_zero():
    assert service_ratio(Decimal(1), Decimal('1e2000000')) == Decimal('1e-2000000')


@pytest.mark.parametrize('where', ['capture', 'package', 'evaluation'])
def test_business_issue_entities_must_remain_in_captured_scope(where):
    snapshot, data = snapshot_data(), package_data()
    bad = issue('UNKNOWN_CAPABILITY', 'WARNING', 'product', UUID(int=900))
    if where == 'capture':
        snapshot['issues'] = [bad]
    elif where == 'package':
        data['issues'] = [bad]
    else:
        data['evaluations'][0]['issues'] = [bad]
    with pytest.raises(ValueError, match='outside captured scope'):
        validate(data, snapshot)
