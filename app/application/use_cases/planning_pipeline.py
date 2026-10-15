"""Explicit resolver-to-/2 bridge; no live setup lookup or default declarations."""
from datetime import datetime
from typing import Annotated, Callable, Literal
from uuid import UUID
from pydantic import Field, model_serializer
from app.application.contracts.offer_admission import OfferAdmission

from app.application.contracts.common import Contract, Nonblank
from app.application.contracts.planning_setup import ResolvedPlanningSetup
from app.application.contracts.decision_capture import InventoryScopeDeclaration
from app.application.contracts.decision_capture_v2 import (
    ExplicitProcurementConfigurationV2, OperationalDecisionInputV2, OperationalPipelineResultV2,
)
from app.application.contracts.decision_execution import DecisionPolicy
from app.application.contracts.procurement import ProcurementOffer, SupplierFee, IngredientCapacity, SupplierLimit
from app.application.decision_snapshot_source_v2 import DecisionSnapshotSourceV2
from app.application.procurement_solver_v2 import ProductCandidateSearch
from app.application.use_cases.decision_pipeline_v2 import execute_operational_pipeline_v2
from app.application.use_cases.decision_capture import utc_now


class PlanningPipelineDeclarations(Contract):
    """Internal composition facts, deliberately not fields the customer may send."""
    forecast_run_id: UUID | None
    inventory_scope: tuple[InventoryScopeDeclaration, ...]
    committed_inbound_state: Literal['CONFIRMED_NONE', 'PRESENT_UNSUPPORTED', 'UNKNOWN']
    committed_inbound_provenance: Nonblank
    no_additional_orders_provenance: Nonblank
    snapshot_policy: DecisionPolicy
    offers: Annotated[tuple[ProcurementOffer, ...], Field(max_length=100)]
    supplier_fees: tuple[SupplierFee, ...]
    capacities: tuple[IngredientCapacity, ...]
    supplier_limits: tuple[SupplierLimit, ...]
    capacity_state: Literal['DECLARED', 'EXPLICIT_NOT_CONFIGURED', 'UNKNOWN']
    supplier_limit_state: Literal['DECLARED', 'EXPLICIT_NOT_CONFIGURED', 'UNKNOWN']
    provenance: Nonblank
    payable_fee_coverage: Literal['COMPLETE', 'UNKNOWN']
    payable_fee_coverage_provenance: Nonblank
    offer_admission: OfferAdmission | None = None

    @model_serializer(mode='wrap')
    def preserve_legacy(self,handler):
        result=handler(self)
        if result.get('offer_admission') is None:result.pop('offer_admission',None)
        return result


def prepare_planning_pipeline(resolution: ResolvedPlanningSetup,
                              declarations: PlanningPipelineDeclarations) -> OperationalDecisionInputV2:
    """Revalidate frozen resolution; reuse actual captured config, never query it."""
    r = ResolvedPlanningSetup.model_validate(resolution)
    d = PlanningPipelineDeclarations.model_validate(declarations)
    # Every unsupported/unknown declaration remains explicit, reaching /2 preflight.
    config = ExplicitProcurementConfigurationV2(policy=r.configuration.policy,
        budget=r.budget, budget_ceiling=r.budget_ceiling, budget_version=r.budget_version,
        **d.model_dump(exclude={'forecast_run_id', 'inventory_scope', 'committed_inbound_state',
            'committed_inbound_provenance', 'no_additional_orders_provenance', 'snapshot_policy'}))
    return OperationalDecisionInputV2(semantics_version='operational_decision/2',
        store_id=r.configuration.store_id, forecast_run_id=d.forecast_run_id,
        cutoff_date=r.cutoff_date, requirements=r.requirements, inventory_scope=d.inventory_scope,
        committed_inbound_state=d.committed_inbound_state,
        committed_inbound_provenance=d.committed_inbound_provenance,
        no_additional_orders_provenance=d.no_additional_orders_provenance,
        snapshot_policy=d.snapshot_policy, procurement=config)


def execute_planning_pipeline(resolution: ResolvedPlanningSetup,
        declarations: PlanningPipelineDeclarations, source: DecisionSnapshotSourceV2,
        search_factory: Callable[..., ProductCandidateSearch],
        clock: Callable[[], datetime] = utc_now) -> OperationalPipelineResultV2:
    return execute_operational_pipeline_v2(prepare_planning_pipeline(resolution, declarations),
                                           source, search_factory, clock)
