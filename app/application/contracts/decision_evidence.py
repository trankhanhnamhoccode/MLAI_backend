"""Immutable internal wording input. Not a model response or public HTTP DTO."""
from typing import Literal
from uuid import UUID
from fractions import Fraction

from pydantic import AwareDatetime, model_validator

from app.application.contracts.auth import DTO
from app.application.contracts.decision_temporal import OperationalBasis
from app.application.contracts.decision_execution import SourceReference
from app.application.contracts.planning_public import (
    RunConfiguration, RunScope, ForecastView, ExecutionView, StrategyResult, Option,
)
from app.application.contracts.planning_inspection import Explanation, IngredientDetail
from app.application.contracts.planning_setup import PlanningRequest
from app.application.planning_serialization import digest


class EvidenceIdentity(DTO):
    run_id: UUID
    store_id: UUID
    aggregate_digest: str
    input_digest: str | None
    result_digest: str | None
    request_digest: str
    storage_version: str
    package_schema_version: int
    result_schema_version: str | None
    capture_schema_version: str | None
    accepted_at: AwareDatetime
    started_at: AwareDatetime | None
    finished_at: AwareDatetime | None
    captured_at: AwareDatetime | None


class IngredientIdentity(DTO):
    ingredient_id: UUID
    unit: str
    name: str | None
    name_availability: Literal['captured', 'not_captured']


class OptionIdentity(DTO):
    option_id: str
    source_strategies: tuple[Literal['lean', 'balanced', 'protected'], ...]
    eligible: bool


class EvidenceOverview(DTO):
    status: Literal['completed', 'failed']
    outcome: str | None
    recommendation_available: bool
    request: PlanningRequest
    configuration: RunConfiguration
    temporal_basis: OperationalBasis | None
    scope: RunScope | None
    ingredients: tuple[IngredientIdentity, ...]
    forecast: ForecastView | None
    execution: ExecutionView | None
    strategies: tuple[StrategyResult, ...]
    selection_proof: Literal['BEST_EVALUATED_CANDIDATES_ONLY'] | None
    source_references: tuple[SourceReference, ...]
    options: tuple[OptionIdentity, ...]
    explanation: Explanation
    assumptions: tuple[str, ...]
    omissions: tuple[str, ...]

    @model_validator(mode='after')
    def recommendation(self):
        winner = self.explanation.winner.option_id
        available = self.status == 'completed' and self.outcome == 'recommendation_available'
        if self.recommendation_available != available or available != (winner is not None):
            raise ValueError('Recommendation outcome and winner must agree')
        if winner is not None and not any(o.option_id == winner and o.eligible for o in self.options):
            raise ValueError('Winner must be an eligible retained option')
        if (winner is not None) != (self.explanation.winner.reason_code == 'WINNER_FOUND'):
            raise ValueError('Winner reason and identity disagree')
        if {(o.option_id, o.eligible, o.source_strategies) for o in self.options} != {
            (o.option_id, o.eligible, o.source_strategies) for o in self.explanation.options
        }:
            raise ValueError('C03 and C08 option identities disagree')
        if len({o.option_id for o in self.options}) != len(self.options):
            raise ValueError('Duplicate option identity')
        return self


class EvidenceReference(DTO):
    evidence_id: str
    pointer: str
    source: Literal['retained_C03', 'retained_C08', 'retained_C05', 'retained_capture']


class DecisionEvidence(DTO):
    schema_version: Literal['decision_evidence/1'] = 'decision_evidence/1'
    identity: EvidenceIdentity
    overview: EvidenceOverview
    option: Option | None
    ingredient: IngredientDetail | None
    references: tuple[EvidenceReference, ...]

    @model_validator(mode='after')
    def scope_and_references(self):
        if (self.overview.explanation.run_id, self.overview.explanation.result_digest) != (self.identity.run_id, self.identity.result_digest):
            raise ValueError('Explanation belongs to another retained Run')
        if self.option is not None:
            brief = next((o for o in self.overview.options if o.option_id == self.option.option_id), None)
            if brief is None or (brief.eligible, brief.source_strategies) != (self.option.eligible, self.option.source_strategies):
                raise ValueError('Option is outside retained scope')
            option = self.option
            costs = option.costs
            exact = lambda q: Fraction(int(q.numerator), int(q.denominator))
            if costs.currency != self.overview.configuration.budget.currency or exact(costs.purchase) + exact(costs.payable_fees) != exact(costs.total):
                raise ValueError('Retained cost components/currency disagree')
            if sum((exact(f.amount) for f in costs.fee_components), Fraction()) != exact(costs.payable_fees):
                raise ValueError('Retained fee components disagree')
            products = {p.product_id: p.selling_unit for p in self.overview.scope.menu_products} if self.overview.scope else {}
            ingredients = {i.ingredient_id: i.unit for i in self.overview.ingredients}
            keys = [(s.product_id, s.path) for s in option.product_services]
            expected = {(p, path) for p in self.overview.scope.computed_product_ids for path in ('LOW', 'BASE', 'HIGH')} if self.overview.scope else set()
            if len(set(keys)) != len(keys) or set(keys) != expected:
                raise ValueError('Per-Product/path service coverage is missing or duplicated')
            for service in option.product_services:
                if service.unit != products.get(service.product_id):
                    raise ValueError('Product service unit differs from retained scope')
                requested, fulfilled = exact(service.requested), exact(service.fulfilled)
                if fulfilled + exact(service.lost_sales) != requested:
                    raise ValueError('Product service quantities disagree')
                ratio = Fraction(int(service.service.numerator), int(service.service.denominator)) if service.service else None
                if ratio != (fulfilled / requested if requested else None):
                    raise ValueError('Service ratio is missing or inconsistent')
            for fact in (*option.purchases, *option.ingredient_balances):
                if ingredients.get(fact.ingredient_id) != fact.unit:
                    raise ValueError('Ingredient unit differs from computed scope')
        if self.ingredient is not None:
            row = self.ingredient
            if (row.run_id, row.result_digest) != (self.identity.run_id, self.identity.result_digest):
                raise ValueError('Ingredient belongs to another Run')
            if not any(i.ingredient_id == row.ingredient_id and i.unit == row.unit for i in self.overview.ingredients):
                raise ValueError('Ingredient is outside computed scope')
            if row.selected_option_id != (self.option.option_id if self.option else None):
                raise ValueError('Ingredient and option context differ')
        if self.references != references_for(self.identity, self.overview, self.option, self.ingredient):
            raise ValueError('Dangling, foreign or altered evidence reference')
        return self

    def resolve(self, evidence_id: str):
        """Resolve only issued refs in this scoped bundle, never client pointers."""
        ref = next((r for r in self.references if r.evidence_id == evidence_id), None)
        if ref is None:
            raise ValueError('Evidence reference is outside this projection')
        value = self
        for segment in ref.pointer.strip('/').split('/'):
            value = getattr(value, segment)
        return value


def references_for(identity: EvidenceIdentity, overview: EvidenceOverview,
                   option: Option | None, ingredient: IngredientDetail | None) -> tuple[EvidenceReference, ...]:
    paths = [('/overview/' + field, 'retained_C03') for field in (
        'status', 'outcome', 'recommendation_available', 'request', 'configuration',
        'temporal_basis', 'scope', 'forecast', 'execution', 'strategies', 'options')]
    paths += [('/overview/explanation', 'retained_C08'),
              ('/overview/selection_proof', 'retained_capture'),
              ('/overview/source_references', 'retained_capture'),
              ('/overview/ingredients', 'retained_capture'),
              ('/overview/assumptions', 'retained_capture'),
              ('/overview/omissions', 'retained_capture')]
    if option is not None:
        paths += [('/option/' + field, 'retained_C03') for field in type(option).model_fields]
    if ingredient is not None:
        paths += [('/ingredient/' + field, 'retained_C05') for field in type(ingredient).model_fields]
    context = (identity.model_dump(mode='json'), option.option_id if option else None,
               str(ingredient.ingredient_id) if ingredient else None)
    return tuple(EvidenceReference(evidence_id='ev-' + digest('decision_evidence/1', [context, path]),
                                   pointer=path, source=source) for path, source in paths)
