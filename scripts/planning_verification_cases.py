"""Two independent Ingredients, one demand day: hand-solvable BASE95 fixtures."""
from datetime import timedelta
from fractions import Fraction
from itertools import product
from uuid import UUID

from scripts.procurement_demo_cases import snapshot, envelope
from scripts.procurement_v2_demo_cases import upgrade, path
from scripts.decision_capture_v2_demo_cases import SyntheticSnapshotSourceV2
from app.application.contracts.decision_capture import OperationalFacts
from app.application.contracts.decision_capture_v2 import OperationalDecisionInputV2, OperationalFactsV2
from app.application.contracts.decision_execution import DecisionPolicy
from app.application.contracts.forecast_execution import PreparedForecastInput
from app.application.forecast_serialization import serialize_prepared
from app.application.use_cases.planning_setup import resolve_planning_setup
from app.application.use_cases.planning_pipeline import PlanningPipelineDeclarations, execute_planning_pipeline
from app.infrastructure.procurement_milp_v2 import NativeProductSearch


def small_case(kind):
    if kind not in {'stock', 'purchase', 'infeasible'}:
        raise ValueError('Unknown synthetic case')
    stock = 20 if kind == 'stock' else 0
    budget = {'stock': '0', 'purchase': '10', 'infeasible': '9'}[kind]
    data = snapshot([[10, 0, 0, 0, 0, 0, 0], [20, 0, 0, 0, 0, 0, 0]],
                    [{0: 2}, {1: 1}], [(0, str(stock), None), (1, str(stock), None)])
    cutoff = data['request']['cutoff_date']
    for ingredient in data['ingredients']:
        ingredient['expiry_tracking'] = True
    for lot in data['lots']:
        lot['expiry_date'] = cutoff + timedelta(days=7)
    data['policy'] = DecisionPolicy().model_dump()
    # Native-only purchasing case, so production enumeration cannot mask a native miss.
    data = upgrade(envelope(data, [dict(ingredient=0, pack='10', cost='2', upper=2, shelf=6),
        dict(ingredient=1, pack='10', cost='3', upper=2, shelf=6)], budget=budget,
        certification='DISABLED' if kind == 'purchase' else 'EXACT_ENUMERATION', limit=9), [path('BASE', '.95')])
    p = data['prepared']; r = p['request']
    retained = PreparedForecastInput(request=dict(store_id=r['store_id'], product_ids=r['product_ids'],
        cutoff_date=cutoff, history_start_date=cutoff), timezone=p['timezone'],
        products=tuple(dict(product_id=x['product_id'], selling_unit=x['selling_unit']) for x in p['products']),
        observations=(), forecast_dates=tuple(cutoff + timedelta(days=n) for n in range(1, 8)))
    digest = serialize_prepared(retained).digest
    forecast = dict(id=r['forecast_run_id'], store_id=r['store_id'], status='COMPLETED',
        training_start_date=cutoff, training_end_date=cutoff, forecast_start_date=cutoff+timedelta(days=1),
        forecast_end_date=cutoff+timedelta(days=7), input_fingerprint=digest,
        model_type='historical_quantile_baseline', model_version='1', artifact_key=None,
        completed_at=p['inventory_as_of']-timedelta(hours=1), retained=retained,
        retained_digest=digest, execution=None, predictions=tuple(dict(id=UUID(int=5000+n),
            store_id=r['store_id'], forecast_run_id=r['forecast_run_id'],
            **{k:v for k,v in point.items() if k!='unit'}) for n,point in enumerate(p['forecast']['predictions'])))
    facts = OperationalFacts(captured_at=p['inventory_as_of'],
        store=dict(id=r['store_id'], timezone=p['timezone'], currency=p['currency']), forecast=forecast,
        products=p['products'], ingredients=p['ingredients'], recipes=p['recipes'], lots=p['lots'],
        supplier_terms=p['supplier_terms'], constraints=p['constraints'], source_times=())
    wrapped = OperationalFactsV2(facts=facts, catalog=tuple(dict(store_id=r['store_id'],
        product_id=x.product_id, name='SYNTHETIC '+str(n), selling_unit=x.selling_unit, active=True)
        for n,x in enumerate(facts.products)), ingredient_scope_ids=tuple(i.ingredient_id for i in facts.ingredients),
        supplier_term_scope=tuple(dict(store_id=t.store_id, term_id=t.id, ingredient_id=t.ingredient_id,
            supplier_id=t.supplier_id) for t in facts.supplier_terms), problems=())
    internal = OperationalDecisionInputV2(semantics_version='operational_decision/2',
        store_id=r['store_id'], forecast_run_id=r['forecast_run_id'], cutoff_date=cutoff, requirements=data['requirements'],
        inventory_scope=tuple(dict(ingredient_id=i.ingredient_id, state='COMPLETE_CURRENT_LOTS',
            provenance='SYNTHETIC complete stock, including explicit zero') for i in facts.ingredients),
        committed_inbound_state='CONFIRMED_NONE', committed_inbound_provenance='SYNTHETIC explicitly none',
        no_additional_orders_provenance='SYNTHETIC one order', snapshot_policy=p['policy'], procurement=dict(
            policy=data['policy'], offers=data['offers'], budget=data['budget'], budget_ceiling=data['budget'],
            budget_version='small-budget/1', supplier_fees=[], capacities=[], supplier_limits=[],
            capacity_state='EXPLICIT_NOT_CONFIGURED', supplier_limit_state='EXPLICIT_NOT_CONFIGURED',
            provenance='SYNTHETIC explicit small domain', payable_fee_coverage='COMPLETE',
            payable_fee_coverage_provenance='SYNTHETIC no payable purchase/delivery fees'))
    config = dict(store_id=r['store_id'], currency=p['currency'], timezone=p['timezone'], read_at=facts.captured_at,
        configuration_version='small-config/1', provenance='SYNTHETIC hand-calculated source', consistency='UNSPECIFIED',
        defaults=dict(version='BASE95/1', updated_at=facts.captured_at,
            requirements=dict(paths=[dict(path='BASE', min_fill_rate_percent='95', product_overrides=[])], budget_limit=None)),
        budget_ceiling=dict(amount=budget, currency=p['currency'], version='small-budget/1', updated_at=facts.captured_at,
            provenance='SYNTHETIC fixed test budget'), saved=None, products=wrapped.catalog, policy=internal.procurement.policy)
    request = dict(requirements_mode='default', forecast_start_date=(cutoff+timedelta(days=1)).isoformat(), default_requirements_version='BASE95/1')
    declarations = PlanningPipelineDeclarations(forecast_run_id=internal.forecast_run_id,
        inventory_scope=internal.inventory_scope, committed_inbound_state=internal.committed_inbound_state,
        committed_inbound_provenance=internal.committed_inbound_provenance,
        no_additional_orders_provenance=internal.no_additional_orders_provenance, snapshot_policy=internal.snapshot_policy,
        **internal.procurement.model_dump(exclude={'policy', 'budget', 'budget_ceiling', 'budget_version'}))
    return request, config, declarations, wrapped


def independent_oracle(kind):
    """Nine vectors, independent arithmetic; no production evaluator or serving call.

    P0 requests10 servings, uses2g each; P1 requests20, uses1g. All demand is on
    first day and independent Ingredients remove allocation contention. Stock and
    all arrivals are usable then, capacities unconfigured, MOQ1, bounds2, fees NONE.
    Thus fulfilled=min(requested,(stock+10*packs)/recipe_quantity), exactly.
    """
    stock = 20 if kind == 'stock' else 0
    budget = {'stock': 0, 'purchase': 10, 'infeasible': 9}[kind]
    rows = []
    for counts in product(range(3), repeat=2):
        outlay = 2*counts[0]+3*counts[1]
        served = (min(Fraction(10), Fraction(stock+10*counts[0], 2)),
                  min(Fraction(20), Fraction(stock+10*counts[1])))
        customer = served[0] >= Fraction(19,2) and served[1] >= 19
        rows.append(dict(counts=counts, outlay=outlay, hard_valid=outlay<=budget,
                         customer_pass=customer and outlay<=budget,
                         served=tuple(str(x) for x in served)))
    passing = [x for x in rows if x['customer_pass']]
    return dict(scope='CAPTURED_FINITE_DOMAIN_ONLY', domain_size=9, evaluated=9, rows=rows,
                passing=passing, minimum_outlay=min((x['outlay'] for x in passing), default=None))


def run_case(kind):
    request, config, declarations, facts = small_case(kind)
    resolved = resolve_planning_setup(request, config)
    if resolved.status != 'RESOLVED':
        raise ValueError('Small-case setup rejected')
    native_calls = []
    def native(*args):
        native_calls.append(True)
        return NativeProductSearch(*args)
    result = execute_planning_pipeline(resolved.resolution, declarations,
        SyntheticSnapshotSourceV2(facts), native, lambda:facts.facts.captured_at)
    return resolved, result, len(native_calls)
