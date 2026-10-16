"""Hand-authored retained read contracts; never create a run or invoke a solver."""
from contextlib import contextmanager
from datetime import datetime, timezone
from datetime import date
from fractions import Fraction
from types import SimpleNamespace as NS
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.application.contracts import planning_public as p
from app.application.contracts.decision_evidence import DecisionEvidence
from app.application.contracts.planning_setup import PlanningRequest, StoredRequirements
from app.application.contracts.auth import AuthError
from app.application.contracts.planning_configuration import ConfigurationError
from app.application.decision_evidence_projection import project_evidence
from app.application.planning_public_projection import quantity, notice
from app.application.planning_serialization import digest
from app.application.contracts.planning_run import PlanningPersistenceError

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def no_business_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Evidence must not execute business computations')
    for module, names in (
        ('app.application.use_cases.procurement', ('_evaluate',)),
        ('app.application.use_cases.procurement_selection', ('select_winner', 'selection_facts')),
        ('app.application.use_cases.bom', ('expand_bom',)),
        ('app.domain.decision.serving', ('simulate',)),
    ):
        import importlib
        for name in names:
            monkeypatch.setattr(importlib.import_module(module), name, forbidden)


def fixture_pair(*, winner='option-a', status='completed', partial=False, result=True):
    request = PlanningRequest(requirements_mode='custom', forecast_start_date='2026-10-15',
        requirements={'paths': [{'path': 'BASE', 'min_fill_rate_percent': '50'}]})
    config = p.RunConfiguration(requirements_mode='custom',
        effective_requirements=StoredRequirements(budget_limit=None,
            paths=({'path': 'BASE', 'min_fill_rate_percent': '50', 'product_overrides': ()},)),
        budget=p.BudgetAtAcceptance(limit='100', currency='VND', ceiling_at_acceptance='100', ceiling_version='budget-1'),
        default_version=None, saved_reference=None)
    products = tuple(p.PlanningProductBrief(product_id=UUID(int=i), name='retained-' + str(i), selling_unit=u)
                     for i, u in ((11, 'cup'), (12, 'piece'), (13, 'box')))
    scope = p.RunScope(menu_products=products, computed_product_ids=(UUID(int=11), UUID(int=12)),
        excluded_products=(p.Exclusion(product_id=UUID(int=13), code='RECIPE_MISSING', field='recipe',
            affected_dates=(), ingredient_ids=(), message='Missing retained recipe', suggested_action='New run',
            requirement_overrides=(p.ExcludedOverride(path='BASE', target_percent='90'),)),),
        menu_count=3, computed_count=2, coverage_status='partial')
    strategy = p.StrategyResult(strategy='balanced', construction_path='BASE', option_id='option-a',
        execution='INCOMPLETE', termination='TIME_LIMIT', customer_pass=True, construction_pass=False,
        selection_kind='CUSTOMER_PASS_FALLBACK', customer_feasibility='PASS_EXISTS', construction_feasibility='UNKNOWN',
        proof='UNPROVEN', proof_scope='CAPTURED_FINITE_DOMAIN_ONLY', domain_size='120', search_complete=False,
        customer_gaps=(), construction_gaps=(), diagnostic=None)
    services = tuple(p.ProductService(product_id=UUID(int=i), unit=u, path=path,
        requested=quantity(2), fulfilled=quantity(1), lost_sales=quantity(1),
        service=p.Service(numerator='1', denominator='2', percent_view='50'))
        for i, u in ((11, 'cup'), (12, 'piece')) for path in ('LOW', 'BASE', 'HIGH'))
    option = p.Option(option_id='option-a', source_strategies=('balanced',), eligible=winner is not None,
        rejection_reasons=() if winner else ('RELATED_BLOCKER',), not_selected_reason=None,
        costs=p.Costs(currency='VND', purchase=quantity(0), payable_fees=quantity(0), delivery_fees=None,
            fee_classification='NONE', total=quantity(0), fee_components=()), purchases=(),
        product_services=services, ingredient_balances=(), requirements_assessment=(
            p.Assessment(product_id=UUID(int=13), path='BASE', target_percent='90',
                applied_source='product_override', status='NOT_EVALUATED', shortfall=None),), issues=())
    other = p.Option(**{**option.model_dump(), 'option_id': 'option-b', 'source_strategies': ('protected',)})
    outcome = 'execution_error' if status == 'failed' else 'recommendation_available' if winner else 'no_eligible_candidate'
    output = p.PlanningResult(completeness='partial' if partial else 'full', strategies=(strategy,),
        options=(option, other), winner_option_id=winner, winner_reason='WINNER_FOUND' if winner else 'NO_ELIGIBLE_CANDIDATE',
        warnings=(notice('NONCURRENT_PLANNING_CURRENT_FACTS'),)) if result else None
    if not result:
        outcome = 'execution_error' if status == 'failed' else 'computation_blocked'
    view = p.RunView(run_id=UUID(int=1), store_id=UUID(int=2), status=status, outcome=outcome,
        accepted_at=NOW, started_at=NOW, finished_at=NOW, response_version='aggregate-1', request=request,
        configuration=config, operational_basis=None, forecast=None, scope=scope, execution=None, result=output, errors=())
    exclusion = NS(product_id=UUID(int=13), reasons=(NS(code='RECIPE_MISSING'),), affected_dates=())
    prepared = NS(ingredients=(NS(ingredient_id=UUID(int=20), unit='kg'), NS(ingredient_id=UUID(int=21), unit='l')),
        assumptions=('RETAINED_ASSUMPTION',), source_references=())
    capture = NS(prepared=prepared, captured_at=NOW, exclusions=(exclusion,), problems=(), semantics_version='operational_capture/2')
    retained = NS(semantics_version='operational_pipeline/2', problems=(), bom=None, comparison=None,
        selection=NS(proof='BEST_EVALUATED_CANDIDATES_ONLY') if result else None)
    record = NS(run_id=view.run_id, store_id=view.store_id, status=status, outcome=outcome,
        input_digest='input-1', request_digest='request-1', result_digest='result-1' if result else None, storage_version='planning_storage/1',
        package_schema_version=1, accepted_at=NOW, capture=capture, public_capture=None, declarations=None,
        result=retained if result else None, error_code='PROCESS_INTERRUPTED' if status == 'failed' else None)
    return record, view


def test_scoped_exact_projection_roundtrip_and_references():
    record, view = fixture_pair(partial=True)
    overview = project_evidence(record, view)
    assert overview.option is None and overview.ingredient is None
    assert overview.overview.recommendation_available
    evidence = project_evidence(record, view, option_id='option-a')
    assert evidence.option.product_services == view.result.options[0].product_services
    assert {s.unit for s in evidence.option.product_services} == {'cup', 'piece'}
    assert evidence.option.costs.total.decimal_view == '0'
    assert evidence.option.costs.delivery_fees is None
    assert evidence.overview.strategies[0].proof == 'UNPROVEN'
    assert evidence.overview.selection_proof == 'BEST_EVALUATED_CANDIDATES_ONLY'
    assert evidence.overview.strategies[0].execution == 'INCOMPLETE'
    assert evidence.overview.strategies[0].construction_feasibility == 'UNKNOWN'
    assert evidence.overview.assumptions == ('RETAINED_ASSUMPTION',)
    assert evidence.overview.explanation.availability == 'partial'
    assert evidence.overview.explanation.exclusions[0].product_id == UUID(int=13)
    assert evidence.overview.scope.excluded_products[0].requirement_overrides[0].status == 'NOT_EVALUATED'
    assert evidence.overview.ingredients[0].name is None
    assert evidence.overview.explanation.warnings[0].code == 'NONCURRENT_PLANNING_CURRENT_FACTS'
    assert DecisionEvidence.model_validate_json(evidence.model_dump_json()) == evidence
    for ref in evidence.references:
        evidence.resolve(ref.evidence_id)
    assert project_evidence(record, view, option_id='option-a').references == evidence.references
    with pytest.raises(ValidationError):
        evidence.option.costs.currency = 'USD'


@pytest.mark.parametrize('status,result', [('completed', True), ('failed', True), ('failed', False), ('completed', False)])
def test_no_winner_failed_missing_not_promoted(status, result):
    record, view = fixture_pair(winner=None, status=status, partial=True, result=result)
    evidence = project_evidence(record, view)
    assert not evidence.overview.recommendation_available
    assert evidence.overview.explanation.winner.option_id is None
    assert 'ZERO_PURCHASE_BASELINE_NOT_PROJECTED' in evidence.overview.omissions
    if not result:
        assert evidence.overview.explanation.evidence_availability == 'not_evaluated'


def test_ingredient_captured_vs_simulated_nullable_and_exact(monkeypatch):
    from app.application.contracts.decision_temporal import OperationalBasis
    record, view = fixture_pair()
    basis = OperationalBasis(version='operational_basis/1', kind='HYPOTHETICAL_CURRENT_CAPTURE',
        captured_at=NOW, timezone='UTC', local_capture_date=date(2026, 10, 15),
        planning_start_date=date(2026, 10, 16), assumptions=('CURRENT_FACTS_ARE_HYPOTHETICAL',))
    view = view.model_copy(update={'operational_basis': basis})
    prepared = record.capture.prepared
    prepared.assumptions = basis.assumptions
    prepared.request = NS(cutoff_date=date(2026, 10, 14))
    prepared.products, prepared.recipes, prepared.supplier_terms = (), (), ()
    prepared.lots = (NS(id=UUID(int=31), ingredient_id=UUID(int=20), on_hand_quantity='3', unit='kg',
        received_date=None, expiry_date=None, supplier_id=None, unit_cost=None),)
    record.capture.source = None
    record.capture.request = NS(inventory_scope=())
    record.public_capture = NS(ingredient_labels=(NS(ingredient_id=UUID(int=20), name='retained name'),))
    record.result.procurement = None
    missing = project_evidence(record, view, ingredient_id=UUID(int=20))
    assert missing.ingredient.daily_balances is None
    assert missing.ingredient.captured_stock.lots[0].quantity.decimal_view == '3'
    assert missing.ingredient.captured_stock.lots[0].unit_cost is None
    assert missing.ingredient.captured_stock.scope_declaration == 'UNKNOWN'
    assert missing.ingredient.display_name == 'retained name'
    daily = NS(ingredient_id=UUID(int=20), path_id='BASE', day=date(2026, 10, 15), unit='kg',
        requested=Fraction(4), available=Fraction(3), shortage=Fraction(1), consumed=Fraction(3),
        expired=Fraction(0), other_waste=Fraction(0), ending=Fraction(0))
    evaluation = NS(status='COMPLETE', ingredients=(daily,), lots=(), contributions=())
    record.result.procurement = NS(strategies=(NS(strategy='BALANCED', candidate=NS(evaluation=evaluation)),))
    known = project_evidence(record, view, ingredient_id=UUID(int=20))
    assert known.ingredient.daily_balances[0].shortage.decimal_view == '1'
    assert known.ingredient.daily_balances[0].ending.decimal_view == '0'
    assert known.ingredient.captured_stock.lots[0].quantity.decimal_view == '3'
    assert known.overview.temporal_basis.kind == 'HYPOTHETICAL_CURRENT_CAPTURE'
    assert known.overview.assumptions == basis.assumptions
    # Live-like labels/config changes are not consulted by either projector.
    assert known.ingredient.name_availability == 'captured'
    assert DecisionEvidence.model_validate_json(known.model_dump_json()) == known


def test_nonzero_cost_components_and_reduced_fraction_display():
    record, view = fixture_pair()
    raw = view.result.options[0].model_dump()
    raw['costs'] = p.Costs(currency='VND', purchase=quantity(Fraction(1, 3)), payable_fees=quantity(2),
        delivery_fees=None, fee_classification='PAYABLE_FEE_TYPE_NOT_CAPTURED', total=quantity(Fraction(7, 3)),
        fee_components=(p.PlanningFeeComponent(basis='SUPPLIER_ORDER', entity_id=UUID(int=41), amount=quantity(2)),))
    raw['purchases'] = (p.Purchase(supplier_term_id=UUID(int=42), supplier_id=UUID(int=41), ingredient_id=UUID(int=20),
        unit='kg', packs=1, quantity=quantity(Fraction(1, 3)), arrival_date=date(2026, 10, 15), expiry_date=None,
        purchase_outlay=quantity(Fraction(1, 3)), payable_fee_components=()),)
    option = p.Option(**raw)
    result = view.result.model_copy(update={'options': (option, view.result.options[1])})
    evidence = project_evidence(record, view.model_copy(update={'result': result}), option_id='option-a')
    assert evidence.option.costs.total.numerator == '7'
    assert evidence.option.costs.total.denominator == '3'
    assert evidence.option.costs.delivery_fees is None
    assert evidence.option.purchases[0].unit == 'kg'
    raw = evidence.model_dump(mode='json')
    raw['option']['costs']['purchase']['decimal_view'] = '0.34'
    with pytest.raises(ValidationError): DecisionEvidence.model_validate(raw)


def test_zero_demand_keeps_undefined_service_not_false_or_zero():
    record, view = fixture_pair()
    option = view.result.options[0]
    service = option.product_services[0].model_copy(update={
        'requested': quantity(0), 'fulfilled': quantity(0), 'lost_sales': quantity(0), 'service': None})
    option = option.model_copy(update={'product_services': (service, *option.product_services[1:])})
    result = view.result.model_copy(update={'options': (option, view.result.options[1])})
    evidence = project_evidence(record, view.model_copy(update={'result': result}), option_id='option-a')
    assert evidence.option.product_services[0].service is None
    assert evidence.option.product_services[0].requested.decimal_view == '0'


def test_false_recommendation_and_foreign_context_rejected():
    record, view = fixture_pair(winner=None)
    with pytest.raises(ValueError, match='identity'):
        project_evidence(record, view.model_copy(update={'outcome': 'recommendation_available'}))
    record.outcome = 'recommendation_available'
    with pytest.raises(ValidationError, match='Recommendation'):
        project_evidence(record, view.model_copy(update={'outcome': 'recommendation_available'}))
    record.outcome = view.outcome
    with pytest.raises(ValueError, match='identity'):
        project_evidence(record, view.model_copy(update={'store_id': UUID(int=999)}))
    with pytest.raises(ConfigurationError) as error:
        project_evidence(record, view, option_id='foreign-option')
    assert error.value.code == 'OPTION_NOT_FOUND'
    with pytest.raises(ConfigurationError) as error:
        project_evidence(record, view, ingredient_id=UUID(int=999))
    assert error.value.code == 'INGREDIENT_NOT_IN_RUN'


@pytest.mark.parametrize('change', ['ref', 'run', 'store', 'option', 'currency', 'service', 'unit', 'cost'])
def test_forged_or_dangling_evidence_rejected(change):
    record, view = fixture_pair()
    evidence = project_evidence(record, view, option_id='option-a')
    data = evidence.model_dump(mode='json')
    if change == 'ref': data['references'][0]['pointer'] = '/option/foreign'
    if change in ('run', 'store'): data['identity'][change + '_id'] = str(UUID(int=999))
    if change == 'option': data['option']['option_id'] = 'foreign'
    if change == 'currency': data['option']['costs']['currency'] = 'USD'
    if change == 'service': data['option']['product_services'][0].pop('service')
    if change == 'unit': data['option']['product_services'][0]['unit'] = 'kg'
    if change == 'cost': data['option']['costs']['total'] = quantity(1).model_dump()
    with pytest.raises(ValidationError): DecisionEvidence.model_validate(data)
    other = project_evidence(record, view, option_id='option-b')
    with pytest.raises(ValueError): other.resolve(evidence.references[0].evidence_id)


def test_actual_application_auth_precedes_materialization_and_rechecks(monkeypatch):
    from app.application.use_cases import planning_public as public
    record, view = fixture_pair()
    allowed = set(public.READ_PERMISSIONS)
    events = []
    class Auth:
        def _resolve(self, session, token):
            if token != 'valid': raise AuthError('UNAUTHENTICATED', 401)
        def authorize_in_session(self, session, token, store, permissions):
            events.append('authorize')
            assert permissions == public.READ_PERMISSIONS
            if store != view.store_id: raise AuthError('RESOURCE_NOT_FOUND', 404)
            if token != 'valid': raise AuthError('UNAUTHENTICATED', 401)
            if not set(permissions) <= allowed: raise AuthError('PERMISSION_DENIED', 403)
            return None, None, None
    @contextmanager
    def session(engine):
        yield NS(commit=lambda: None)
    class Repo:
        def __init__(self, session): pass
        def owning_store(self, run_id):
            return view.store_id if run_id == record.run_id else UUID(int=999) if run_id == UUID(int=998) else None
        def get(self, store, run_id):
            events.append('materialize')
            return record
    def read(row, *, evidence):
        assert evidence
        return record, view
    record.public_acceptance = NS()
    service = public.PublicPlanning.__new__(public.PublicPlanning)
    service.engine, service.auth, service.retained = None, Auth(), NS(read=read)
    monkeypatch.setattr(public, 'auth_session', session)
    monkeypatch.setattr(public, 'PlanningRepository', Repo)
    service.assistant_evidence('valid', record.run_id)
    assert events == ['authorize', 'materialize']
    for right in public.READ_PERMISSIONS:
        events.clear()
        allowed.remove(right)
        with pytest.raises(AuthError): service.assistant_evidence('valid', record.run_id)
        assert events == ['authorize']
        allowed.add(right)
    with pytest.raises(AuthError): service.assistant_evidence('revoked-session', record.run_id)
    for foreign_run in (UUID(int=998), UUID(int=997)):
        events.clear()
        with pytest.raises(AuthError) as error: service.assistant_evidence('valid', foreign_run)
        assert error.value.code == 'RESOURCE_NOT_FOUND'
        assert 'materialize' not in events


def test_cache_only_no_cold_decoder_and_hash_changes_fail_closed(monkeypatch):
    import app.application.planning_retained_reads as reads
    row = NS(record_json={'retained': 'one'}, revision=1, id=UUID(int=1), actor_id=UUID(int=3),
        store_id=UUID(int=2), operation='C02', key_digest='key', request_digest='request',
        status='completed', accepted_at=NOW)
    row.record_digest = digest('aggregate', row.record_json)
    cache = reads.VerifiedPlanningReads()
    record, view = fixture_pair()
    def forbidden(row): raise AssertionError('Cold decoder called')
    monkeypatch.setattr(reads, 'decode_row', forbidden)
    with pytest.raises(PlanningPersistenceError, match='EVIDENCE_NOT_VERIFIED'):
        cache.read(row, require_cached=True)
    monkeypatch.setattr(reads, 'decode_row', lambda row: record)
    monkeypatch.setattr(reads, 'project_run', lambda record, **kwargs: view)
    assert cache.read(row) == (record, view)
    monkeypatch.setattr(reads, 'decode_row', forbidden)
    assert cache.read(row, require_cached=True) == (record, view)
    row.record_json['retained'] = 'tampered'
    with pytest.raises(PlanningPersistenceError, match='RESULT_INTEGRITY_UNAVAILABLE'):
        cache.read(row, require_cached=True)
    row.record_digest = digest('aggregate', row.record_json)
    with pytest.raises(PlanningPersistenceError, match='EVIDENCE_NOT_VERIFIED'):
        cache.read(row, require_cached=True)
