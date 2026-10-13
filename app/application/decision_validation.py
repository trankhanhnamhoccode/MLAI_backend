"""Opt-in validation of supplied decision output, not generation or selection."""
from app.application.contracts.decision_execution import PreparedDecisionInput
from app.application.contracts.decision_package import DecisionPackageV1
from app.domain.decision.validation import PATHS, STRATEGIES, arrival_date, exact_equal, exact_product, unique_coverage
from app.domain.forecasting.validation import forecast_dates


def validate_decision_package(prepared: PreparedDecisionInput, package: DecisionPackageV1,
                              *, expected_input_fingerprint: str) -> DecisionPackageV1:
    """Validate supplied outputs; does not compute outputs, rank or persist them.

    Fingerprint is supplied by a future verified capture/serialization adapter;
    S3.1 defines the identity design but does not claim hashing/retention execution.
    """
    prepared = PreparedDecisionInput.model_validate(prepared)
    if prepared.capture_version != 1:
        raise ValueError('Historical DecisionPackageV1 requires capture_version=1')
    package = DecisionPackageV1.model_validate(package)
    prepared.validate_issue_scope(package.issues)
    for evaluation in package.evaluations:
        prepared.validate_issue_scope(evaluation.issues)
    if package.input_fingerprint != expected_input_fingerprint or package.policy != prepared.policy:
        raise ValueError('Input identity/policy must match the validated snapshot')
    if not set(prepared.issues) <= set(package.issues):
        raise ValueError('Package must preserve captured business issues')
    blocked = any(i.kind == 'DATA_BLOCKER' for i in (*prepared.issues, *package.issues))
    if blocked:
        if (package.recommendation.status != 'DATA_BLOCKED' or package.candidates or
                package.evaluations or package.paths or package.bom):
            raise ValueError('Data-blocked output must not manufacture computed plans')
        return package
    if package.recommendation.status == 'DATA_BLOCKED':
        raise ValueError('Data-blocked status needs a blocker')
    days = forecast_dates(prepared.request.cutoff_date)
    product_units = {p.product_id: p.selling_unit for p in prepared.products}
    ingredients = {i.ingredient_id: i for i in prepared.ingredients}
    product_keys = {(p, d) for p in product_units for d in days}
    ingredient_keys = {(i, d) for i in ingredients for d in days}
    unique_coverage(tuple(p.path_id for p in package.paths), set(PATHS), 'Demand paths')
    demand = {}
    forecast = {(p.product_id, p.forecast_date): p for p in prepared.forecast.predictions}
    for path in package.paths:
        unique_coverage(tuple((d.product_id, d.day) for d in path.demands), product_keys, 'Product demands')
        for d in path.demands:
            expected = getattr(forecast[d.product_id, d.day], {'LOW': 'p25', 'BASE': 'p50', 'HIGH': 'p75'}[path.path_id])
            if d.unit != product_units[d.product_id] or d.quantity != expected:
                raise ValueError('Demand path must match captured quantile values/units')
            demand[path.path_id, d.product_id, d.day] = d.quantity
    bom_keys = set()
    for recipe in prepared.recipes:
        for day in days:
            if recipe.effective_from <= day and (recipe.effective_to is None or day <= recipe.effective_to):
                bom_keys.update((path, recipe.product_id, day, recipe.id, line.ingredient_id)
                                for path in PATHS for line in recipe.lines)
    unique_coverage(tuple((b.path_id, b.product_id, b.day, b.recipe_id, b.ingredient_id) for b in package.bom),
                    bom_keys, 'BOM contributions')
    if any(b.unit != ingredients[b.ingredient_id].unit for b in package.bom):
        raise ValueError('BOM contribution unit mismatch')
    unique_coverage(tuple(c.strategy for c in package.candidates), set(STRATEGIES), 'Candidates')
    terms = {t.id: t for t in prepared.supplier_terms}
    budgets = [c.value for c in prepared.constraints if c.kind == 'BUDGET_LIMIT']
    for candidate in package.candidates:
        if candidate.currency != prepared.currency:
            raise ValueError('Candidate currency mismatch')
        if len({l.ingredient_id for l in candidate.lines}) != len(candidate.lines):
            raise ValueError('v1 allows one chosen supplier term per Ingredient')
        for line in candidate.lines:
            term = terms.get(line.supplier_term_id)
            if term is None or (line.ingredient_id, line.unit) != (term.ingredient_id, term.unit):
                raise ValueError('Order line must use captured term and exact Ingredient unit')
            if line.packs and line.packs < term.minimum_order_packs:
                raise ValueError('Positive order must activate MOQ')
            if not exact_product(line.quantity, term.pack_size_base_quantity, line.packs) or not exact_product(
                    line.purchase_outlay, term.pack_cost, line.packs):
                raise ValueError('Order quantity/outlay must match whole packs')
            expected_arrival = arrival_date(days[0], term.lead_time_days)
            if line.arrival_date != expected_arrival:
                raise ValueError('Arrival must equal D+1 order date + captured lead days')
            if line.packs and line.arrival_date > days[-1]:
                raise ValueError('Positive order arriving after the horizon cannot serve this one-order plan')
            if term.shelf_life_days is not None:
                if line.expiry_date != arrival_date(expected_arrival, term.shelf_life_days):
                    raise ValueError('Hypothetical expiry must match explicit shelf life')
            elif line.expiry_date is not None or (line.packs and ingredients[line.ingredient_id].expiry_tracking):
                raise ValueError('Unknown shelf life cannot become invented expiry/usable tracked stock')
        if not exact_equal(candidate.purchase_outlay, *(l.purchase_outlay for l in candidate.lines)):
            raise ValueError('Candidate outlay must equal order lines')
        if budgets and candidate.purchase_outlay > budgets[0]:
            raise ValueError('Candidate exceeds hard purchase budget')
    # Equivalence excludes strategy labels and order-line serialization order.
    signatures = {c.strategy: tuple(sorted((l.supplier_term_id, l.ingredient_id, l.unit, l.packs,
                      l.quantity, l.purchase_outlay, l.arrival_date, l.expiry_date) for l in c.lines if l.packs))
                  for c in package.candidates}
    for candidate in package.candidates:
        expected = {s for s, v in signatures.items() if s != candidate.strategy and v == signatures[candidate.strategy]}
        unique_coverage(candidate.equivalent_to, expected, 'Equivalent strategies')
    unique_coverage(tuple((e.strategy, e.path_id) for e in package.evaluations),
                    {(s, p) for s in STRATEGIES for p in PATHS}, 'Evaluations')
    candidates = {c.strategy: c for c in package.candidates}
    for e in package.evaluations:
        if e.status != 'COMPLETE':
            continue
        unique_coverage(tuple((p.product_id, p.day) for p in e.products), product_keys, 'Daily fulfillment')
        unique_coverage(tuple((i.ingredient_id, i.day) for i in e.ingredients), ingredient_keys, 'Daily stock')
        for p in e.products:
            if p.unit != product_units[p.product_id] or p.requested != demand[e.path_id, p.product_id, p.day]:
                raise ValueError('Fulfillment must evaluate the common demand path')
        for i in e.ingredients:
            if i.unit != ingredients[i.ingredient_id].unit:
                raise ValueError('Daily inventory unit mismatch')
            previous = next((r for r in e.ingredients if r.ingredient_id == i.ingredient_id and r.day < i.day
                             and r.day == arrival_date(i.day, -1)), None)
            if previous is not None and i.opening != previous.ending_usable:
                raise ValueError('Consecutive daily balances must connect')
            if i.day == days[0] and not exact_equal(i.opening, *(lot.on_hand_quantity for lot in prepared.lots
                    if lot.ingredient_id == i.ingredient_id and
                    (lot.received_date is None or lot.received_date <= days[0]))):
                raise ValueError('Initial balance must equal captured actually received inventory')
            lines = [l for l in candidates[e.strategy].lines if l.ingredient_id == i.ingredient_id and l.arrival_date == i.day]
            if not exact_equal(i.arrivals, *(l.quantity for l in lines)):
                raise ValueError('All paths must use the same fixed candidate arrivals')
        m = e.metrics
        if m is None:  # defensive for callers using model_construct
            raise ValueError('Complete evaluation missing metrics')
        if m.selling_unit != next(iter(product_units.values())) or not exact_equal(
                m.requested, *(p.requested for p in e.products)) or not exact_equal(
                m.fulfilled, *(p.fulfilled for p in e.products)):
            raise ValueError('Metrics must match daily Product totals/units')
        if m.purchase_outlay.status != 'KNOWN' or m.purchase_outlay.value != candidates[e.strategy].purchase_outlay:
            raise ValueError('Metrics must retain candidate purchase outlay')
        if any(metric.unit != prepared.currency for metric in (m.purchase_outlay, m.waste_value, m.ending_usable_value)):
            raise ValueError('Value metrics must use Store currency')
        unknown_stock_cost = any(lot.unit_cost is None and lot.on_hand_quantity > 0 and
                                 (lot.received_date is None or lot.received_date <= days[0]) for lot in prepared.lots)
        if unknown_stock_cost:
            # No lot cost attribution exists yet; conservatively retain unknown value.
            if any(i.expired > 0 or i.waste > 0 for i in e.ingredients) and m.waste_value.status != 'UNKNOWN':
                raise ValueError('Positive waste with potentially unknown lot cost cannot claim a known value')
            if any(i.day == days[-1] and i.ending_usable > 0 for i in e.ingredients) and m.ending_usable_value.status != 'UNKNOWN':
                raise ValueError('Positive ending stock with unknown lot cost cannot claim a known value')
    selected = package.recommendation.strategy
    incomplete = any(e.status == 'INCOMPLETE' for e in package.evaluations)
    if incomplete:
        if package.recommendation.status != 'EVALUATION_INCOMPLETE' or selected is not None:
            raise ValueError('All nine evaluations must finish before recommendation')
        return package
    if package.recommendation.status == 'EVALUATION_INCOMPLETE':
        raise ValueError('Incomplete status needs unfinished evaluation evidence')
    eligible = {s: {e.path_id: e for e in package.evaluations if e.strategy == s} for s in STRATEGIES
                if all(e.status == 'COMPLETE' for e in package.evaluations if e.strategy == s)
                and not any(i.kind == 'HARD_VIOLATION' and any(a.strategy in (None, s) for a in i.affected)
                            for i in package.issues)}
    def targets(evaluated):
        base_m, high_m = evaluated['BASE'].metrics, evaluated['HIGH'].metrics
        base = base_m.requested == 0 or base_m.service.value >= prepared.policy.base_service_target
        high = high_m.requested == 0 or high_m.service.value >= prepared.policy.high_service_target
        return 'TARGETS_MET' if base and high else 'BASE_ONLY' if base else 'TARGETS_NOT_MET'
    categories = {s: targets(e) for s, e in eligible.items()}
    best_category = ('TARGETS_MET' if 'TARGETS_MET' in categories.values() else
                     'BASE_ONLY' if 'BASE_ONLY' in categories.values() else
                     'TARGETS_NOT_MET' if categories else 'HARD_INFEASIBLE')
    if package.recommendation.status != best_category:
        raise ValueError('Recommendation outcome must reflect the best eligible service group')
    if selected is not None:
        evaluated = {e.path_id: e for e in package.evaluations if e.strategy == selected}
        if (any(e.status != 'COMPLETE' or any(i.kind in ('DATA_BLOCKER', 'HARD_VIOLATION') for i in e.issues)
                for e in evaluated.values()) or any(i.kind == 'HARD_VIOLATION' and
                    any(a.strategy in (None, selected) for a in i.affected) for i in package.issues)):
            raise ValueError('Selected candidate must have all complete, hard-valid evaluations')
        # Zero demand is vacuously target-satisfying, while the displayed ratio stays undefined.
        expected = targets(evaluated)
        if package.recommendation.status != expected:
            raise ValueError('Recommendation status contradicts selected candidate service evidence')
        if not any(v.strategy == selected for v in package.recommendation.evidence):
            raise ValueError('Recommendation evidence must include selected candidate')
    elif package.recommendation.status == 'HARD_INFEASIBLE':
        if not all(any(e.strategy == s and e.status == 'HARD_INFEASIBLE' for e in package.evaluations) or
                   any(i.kind == 'HARD_VIOLATION' and any(a.strategy in (None, s) for a in i.affected)
                       for i in package.issues) for s in STRATEGIES):
            raise ValueError('Hard-infeasible outcome needs evidence for every candidate')
    return package
