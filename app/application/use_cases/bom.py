"""Pure opt-in BOM boundary. No Session, live queries or DecisionRun persistence."""
from dataclasses import asdict
from pydantic import TypeAdapter, ValidationError

from app.application.contracts.bom import BOMExpansionResult, BOMIssue, IngredientDemandTotal
from app.application.contracts.decision_execution import PreparedDecisionInput
from app.application.contracts.common import NonnegativeDecimal
from app.application.contracts.decision_package import BOMContribution, ProductDemand, ProductDemandPath
from app.domain.demand.arithmetic import BOMArithmeticError
from app.domain.demand.bom import DatedRecipe, DemandPoint, RecipeLine, expand_dated_bom


def _issue_key(issue):
    return ('' if issue.day is None else issue.day.isoformat(), issue.path_id or '', issue.code,
            issue.kind, issue.field, tuple((a.entity, str(a.entity_id), a.strategy or '') for a in issue.affected),
            issue.impact, issue.suggested_action)


def _canonical_snapshot(prepared: PreparedDecisionInput) -> PreparedDecisionInput:
    data = prepared.model_dump()
    for recipe in data['recipes']:
        recipe['lines'] = tuple(sorted(recipe['lines'], key=lambda line: line['ingredient_id']))
    data['assumptions'] = tuple(sorted(data['assumptions']))
    for issue in data['issues']:
        issue['affected'] = tuple(sorted(issue['affected'], key=lambda a: (
            a['entity'], str(a['entity_id']), a['strategy'] or '')))
    data['source_references'] = tuple(sorted(data['source_references'], key=lambda r: (
        r['entity'], r['entity_id'], r['version'] or 0, r['origin'])))
    data['issues'] = tuple(sorted(data['issues'], key=lambda i: _issue_key(BOMIssue.model_validate(i))))
    data['forecast']['warnings'] = tuple(sorted(data['forecast']['warnings'], key=lambda w: (
        w['code'], w['severity'], w['field'], w['entity'], w['impact'], str(w['product_id']))))
    return PreparedDecisionInput.model_validate(data)


def expand_bom(prepared: PreparedDecisionInput) -> BOMExpansionResult:
    prepared = _canonical_snapshot(PreparedDecisionInput.model_validate(prepared))
    paths = tuple(ProductDemandPath(path_id=path, demands=tuple(
        ProductDemand(product_id=p.product_id, day=p.forecast_date, unit=p.unit, quantity=getattr(p, quantile))
        for p in prepared.forecast.predictions)) for path, quantile in (('LOW','p25'),('BASE','p50'),('HIGH','p75')))
    demands = tuple(DemandPoint(path.path_id, d.product_id, d.day, d.quantity) for path in paths for d in path.demands)
    recipes = tuple(DatedRecipe(r.id, r.product_id, r.effective_from, r.effective_to, r.yield_quantity,
                               r.process_loss_rate, tuple(RecipeLine(l.ingredient_id, l.unit, l.quantity) for l in r.lines))
                    for r in prepared.recipes)
    issues = [BOMIssue.model_validate(i.model_dump()) for i in prepared.issues]
    try:
        expansion = expand_dated_bom(demands, recipes)
        # The unchanged shared Pydantic boundary has a narrower finite-number
        # acceptance range than Decimal. Classify only this known numeric failure;
        # malformed output/programming errors must still escape.
        quantity_adapter = TypeAdapter(NonnegativeDecimal)
        for row in (*expansion.contributions, *expansion.totals):
            try:
                quantity_adapter.validate_python(row.quantity)
            except ValidationError as error:
                if any(e['type'] != 'finite_number' for e in error.errors()):
                    raise
                raise BOMArithmeticError('BOM_NUMERIC_BOUNDARY',
                    'Finite Decimal quantity exceeds the existing output contract range',
                    path_id=row.path_id, day=row.day, ingredient_id=row.ingredient_id,
                    product_id=getattr(row, 'product_id', None)) from error
    except BOMArithmeticError as error:
        affected = [{'entity':'product', 'entity_id':error.product_id}] if error.product_id else []
        if error.ingredient_id:
            affected.append({'entity':'ingredient', 'entity_id':error.ingredient_id})
        issues.append(BOMIssue(code=error.code, kind='DATA_BLOCKER', field='quantity', affected=affected,
            day=error.day, path_id=error.path_id, impact=str(error),
            suggested_action='Review numeric range/capacity; do not replace the quantity with zero'))
        status, contributions, totals, paths = 'ARITHMETIC_BLOCKED', (), (), ()
    else:
        if expansion.gaps:
            for gap in expansion.gaps:
                issues.append(BOMIssue(code=gap.code, kind='DATA_BLOCKER', field='recipe', day=gap.day,
                    affected=[{'entity':'product', 'entity_id':gap.product_id}],
                    impact='Dated Product recipe unavailable; whole BOM scope is blocked',
                    suggested_action='Provide a nonempty recipe effective on this planning date'))
            status, contributions, totals, paths = 'DATA_BLOCKED', (), (), ()
        else:
            status = 'COMPLETE'
            contributions = tuple(BOMContribution(**asdict(c)) for c in expansion.contributions)
            totals = tuple(IngredientDemandTotal(**asdict(t)) for t in expansion.totals)
    return BOMExpansionResult(status=status, decision_readiness=(
        'DATA_BLOCKED' if any(i.kind == 'DATA_BLOCKER' for i in issues) else 'NOT_ASSESSED'),
        prepared=prepared, paths=paths, contributions=contributions, totals=totals,
        issues=tuple(sorted(issues, key=_issue_key)))
